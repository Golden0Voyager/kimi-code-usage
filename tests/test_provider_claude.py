"""Tests for the Claude subscription provider."""

import json
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kimi_code_usage.providers import ProviderUsage
from kimi_code_usage.providers.claude import (
    _extract_access_token,
    _is_macos,
    _parse_usage_response,
    _read_oauth_token,
    fetch_claude_usage,
)

# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_lang():
    with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=False):
        yield


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Keep the developer's real shell env from leaking into these tests."""
    for var in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_USAGE_OAUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch):
    """Never touch the real login keychain — reading it prompts the user.

    Tests that exercise the keychain re-patch `_is_macos`/`subprocess.run`.
    """
    monkeypatch.setattr("kimi_code_usage.providers.claude._is_macos", lambda: False)


# The real ``~/.claude/.credentials.json`` shape: ``claudeAiOauth`` is an
# object holding ``accessToken`` / ``refreshToken`` / ``expiresAt`` / ``scopes``.
SAMPLE_CREDENTIALS = {
    "claudeAiOauth": {
        "accessToken": "sk-ant-oat01-test-token",
        "refreshToken": "sk-ant-ort01-test-token",
        "expiresAt": 4102444800000,
        "scopes": ["user:inference", "user:profile"],
    }
}

SAMPLE_TOKEN = "sk-ant-oat01-test-token"


def keychain_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


def make_creds_file(tmp_path: Path, content: dict | None = None) -> Path:
    creds_path = tmp_path / ".credentials.json"
    creds_path.write_text(json.dumps(content or SAMPLE_CREDENTIALS), encoding="utf-8")
    return creds_path


def make_mock_scraper(status: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status
    if json_data is not None:
        mock_resp.json.return_value = json_data
    if text:
        mock_resp.text = text
    mock_scraper = MagicMock()
    mock_scraper.get.return_value = mock_resp
    return mock_scraper


# ──────────────────────────────────────────────────────────────────────────
# _read_oauth_token
# ──────────────────────────────────────────────────────────────────────────


def test_read_oauth_token_from_file(tmp_path):
    """`claudeAiOauth` is an object — the token must come from `.accessToken`."""
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN


def test_read_oauth_token_from_file_accepts_bare_string(tmp_path):
    """Tolerate hand-written files that store the token without the wrapper."""
    creds_path = make_creds_file(tmp_path, {"claudeAiOauth": "bare-token"})
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == "bare-token"


def test_read_oauth_token_from_top_level_token(tmp_path):
    """Some installs record the token at the top level instead of nested."""
    creds_path = make_creds_file(tmp_path, {"accessToken": "top-level-token"})
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        assert _read_oauth_token() == "top-level-token"


def test_read_oauth_token_ignores_empty_access_token(tmp_path):
    """A blank accessToken must not be accepted as a token."""
    creds_path = make_creds_file(tmp_path, {"claudeAiOauth": {"accessToken": ""}})
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        with pytest.raises(FileNotFoundError, match="Claude OAuth token not found"):
            _read_oauth_token()


def test_extract_access_token_rejects_non_mapping():
    assert _extract_access_token(["not", "a", "mapping"]) is None
    assert _extract_access_token(None) is None


def test_is_macos_matches_sys_platform():
    with patch("sys.platform", "darwin"):
        assert _is_macos() is True
    with patch("sys.platform", "linux"):
        assert _is_macos() is False


def test_read_oauth_token_prefers_macos_keychain(tmp_path):
    """On macOS Claude Code stores credentials in the login keychain."""
    creds_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.claude._is_macos", return_value=True), \
         patch("kimi_code_usage.providers.claude.subprocess.run",
               return_value=keychain_result(json.dumps(SAMPLE_CREDENTIALS))) as run, \
         patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN
    argv = run.call_args.args[0]
    assert argv[:2] == ["security", "find-generic-password"]
    assert "Claude Code-credentials" in argv


def test_read_oauth_token_keychain_failure_falls_back_to_file(tmp_path):
    """A non-zero `security` exit must not break the file fallback."""
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude._is_macos", return_value=True), \
         patch("kimi_code_usage.providers.claude.subprocess.run",
               return_value=keychain_result("", returncode=44)), \
         patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN


def test_read_oauth_token_keychain_garbage_falls_back_to_file(tmp_path):
    """Keychain output that is not JSON (e.g. a permission prompt) is ignored."""
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude._is_macos", return_value=True), \
         patch("kimi_code_usage.providers.claude.subprocess.run",
               return_value=keychain_result("not json at all")), \
         patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN


def test_read_oauth_token_keychain_missing_binary_falls_back(tmp_path):
    """A missing/permission-denied `security` binary must be survivable."""
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude._is_macos", return_value=True), \
         patch("kimi_code_usage.providers.claude.subprocess.run",
               side_effect=OSError("security: command not found")), \
         patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN


def test_read_oauth_token_keychain_timeout_falls_back(tmp_path):
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude._is_macos", return_value=True), \
         patch("kimi_code_usage.providers.claude.subprocess.run",
               side_effect=subprocess.TimeoutExpired("security", 5)), \
         patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN


def test_read_oauth_token_skips_keychain_off_macos(tmp_path):
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude.subprocess.run") as run, \
         patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == SAMPLE_TOKEN
    run.assert_not_called()


def test_read_oauth_token_from_env(tmp_path):
    creds_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "env-token"}, clear=False):
        token = _read_oauth_token()
    assert token == "env-token"


def test_read_oauth_token_from_usage_env(tmp_path):
    """`CLAUDE_USAGE_OAUTH_TOKEN` is the name upstream tools conventionally use."""
    creds_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch.dict(os.environ, {"CLAUDE_USAGE_OAUTH_TOKEN": "usage-env-token"}, clear=False):
        token = _read_oauth_token()
    assert token == "usage-env-token"


def test_read_oauth_token_not_found(tmp_path):
    creds_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        with pytest.raises(FileNotFoundError, match="Claude OAuth token not found"):
            _read_oauth_token()


def test_read_oauth_token_bad_json(tmp_path):
    creds_path = tmp_path / ".credentials.json"
    creds_path.write_text("not json", encoding="utf-8")
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        with pytest.raises(FileNotFoundError, match="Claude OAuth token not found"):
            _read_oauth_token()


# ──────────────────────────────────────────────────────────────────────────
# _parse_usage_response
# ──────────────────────────────────────────────────────────────────────────


def test_parse_all_windows():
    data = {
        "five_hour": {"utilization": 0.05},
        "seven_day": {"utilization": 0.23},
        "seven_day_sonnet": {"utilization": 0.10},
        "seven_day_opus": {"utilization": 0.15},
    }
    rows = _parse_usage_response(data)
    assert len(rows) == 4
    labels = [r.label for r in rows]
    assert "5 Hours" in labels
    assert "7 Days" in labels
    assert "7 Days Sonnet" in labels
    assert "7 Days Opus" in labels
    assert rows[0].used == 5.0
    assert rows[0].percent == 5.0
    assert rows[1].used == 23.0


def test_parse_zh():
    with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}, clear=False):
        data = {
            "five_hour": {"utilization": 0.05},
            "seven_day": {"utilization": 0.23},
        }
        rows = _parse_usage_response(data)
        assert "5小时限额" in rows[0].label
        assert "7天用量" in rows[1].label


def test_parse_fallback():
    data = {"unexpected": "format"}
    rows = _parse_usage_response(data)
    assert len(rows) == 1
    assert rows[0].unit == "text"


def test_parse_percent_utilization_is_not_rescaled():
    """The endpoint reports `utilization` as a 0-100 percentage, not a fraction."""
    rows = _parse_usage_response({"five_hour": {"utilization": 15.0}})
    assert rows[0].used == 15.0
    assert rows[0].percent == 15.0
    assert rows[0].remaining == 85.0


def test_parse_fractional_utilization_is_rescaled():
    """0 < v < 1 is the only ambiguous range; treat it as a fraction."""
    rows = _parse_usage_response({"five_hour": {"utilization": 0.15}})
    assert rows[0].used == 15.0


def test_parse_zero_utilization_stays_zero():
    rows = _parse_usage_response({"five_hour": {"utilization": 0}})
    assert rows[0].used == 0.0
    assert rows[0].remaining == 100.0


def test_parse_utilization_above_100_is_clamped():
    rows = _parse_usage_response({"five_hour": {"utilization": 150.0}})
    assert rows[0].used == 100.0
    assert rows[0].percent == 100.0
    assert rows[0].remaining == 0.0


def test_parse_negative_utilization_is_clamped():
    rows = _parse_usage_response({"five_hour": {"utilization": -5.0}})
    assert rows[0].used == 0.0


def test_parse_non_numeric_utilization_falls_back_to_raw():
    rows = _parse_usage_response({"five_hour": {"utilization": "n/a"}})
    assert len(rows) == 1
    assert rows[0].unit == "text"


def test_parse_reset_at_is_kept():
    """`resets_at` is in the response — dropping it loses the reset time."""
    rows = _parse_usage_response(
        {"five_hour": {"utilization": 15.0, "resets_at": "2026-10-19T12:34:56+00:00"}}
    )
    assert rows[0].reset_at is not None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", rows[0].reset_at)


def test_parse_reset_at_z_suffix_and_numeric():
    rows = _parse_usage_response(
        {
            "five_hour": {"utilization": 15.0, "resets_at": "2026-10-19T12:34:56Z"},
            "seven_day": {"utilization": 20.0, "resets_at": 1785044789},
        }
    )
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", rows[0].reset_at)
    # A non-string resets_at is not a timestamp we understand — ignore it.
    assert rows[1].reset_at is None


def test_parse_unparseable_reset_at_is_passed_through():
    rows = _parse_usage_response(
        {"five_hour": {"utilization": 15.0, "resets_at": "soon"}}
    )
    assert rows[0].reset_at == "soon"


def test_parse_missing_reset_at_stays_none():
    rows = _parse_usage_response({"five_hour": {"utilization": 15.0}})
    assert rows[0].reset_at is None


def test_parse_window_without_utilization_is_skipped():
    rows = _parse_usage_response(
        {
            "five_hour": {"resets_at": "2026-10-19T12:34:56Z"},
            "seven_day": {"utilization": 10},
        }
    )
    assert [r.label for r in rows] == ["7 Days"]


# ──────────────────────────────────────────────────────────────────────────
# fetch_claude_usage
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_success(tmp_path):
    creds_path = make_creds_file(tmp_path)

    usage_data = {
        "five_hour": {"utilization": 0.05},
        "seven_day": {"utilization": 0.23},
    }

    mock_scraper = make_mock_scraper(200, usage_data)

    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        rows = await fetch_claude_usage("enabled", "https://api.anthropic.com")

    assert len(rows) == 2
    assert rows[0].provider == "claude"
    assert rows[0].label == "5 Hours"
    assert rows[0].used == 5.0
    assert rows[1].label == "7 Days"
    assert rows[1].used == 23.0


@pytest.mark.asyncio
async def test_fetch_api_error(tmp_path):
    creds_path = make_creds_file(tmp_path)
    mock_scraper = make_mock_scraper(500, text="Server Error")

    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        with pytest.raises(RuntimeError, match="Claude API Error"):
            await fetch_claude_usage("enabled", "https://api.anthropic.com")


@pytest.mark.asyncio
async def test_fetch_unauthorized(tmp_path):
    creds_path = make_creds_file(tmp_path)
    mock_scraper = make_mock_scraper(401, text="Unauthorized")

    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        with pytest.raises(RuntimeError, match="Claude API returned 401/403"):
            await fetch_claude_usage("enabled", "https://api.anthropic.com")


@pytest.mark.asyncio
async def test_fetch_creds_not_found(tmp_path):
    creds_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        with pytest.raises(FileNotFoundError, match="Claude OAuth token not found"):
            await fetch_claude_usage("enabled", "https://api.anthropic.com")


@pytest.mark.asyncio
async def test_fetch_wraps_unexpected_errors(tmp_path):
    """Network failures surface as a RuntimeError, not a raw OSError."""
    creds_path = make_creds_file(tmp_path)
    mock_scraper = MagicMock()
    mock_scraper.get.side_effect = OSError("connection reset by peer")

    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        with pytest.raises(RuntimeError, match="Claude API request failed"):
            await fetch_claude_usage("enabled", "https://api.anthropic.com")


# ──────────────────────────────────────────────────────────────────────────
# dispatch_all integration
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_all_claude_integration(tmp_path):
    from kimi_code_usage.config import AppConfig, ProviderConfig
    from kimi_code_usage.providers import dispatch_all

    config = AppConfig(
        providers={
            "claude": ProviderConfig(api_key="enabled", base_url="https://api.anthropic.com", enabled=True),
        }
    )

    mock_usage = [ProviderUsage(provider="claude", label="5 Hours", used=5.0, limit=100.0, remaining=95.0, percent=5.0, reset_at=None, unit="%")]

    with patch("kimi_code_usage.providers.claude.fetch_claude_usage", new_callable=AsyncMock, return_value=mock_usage):
        results, errors = await dispatch_all(config)

    assert "claude" in results
    assert results["claude"] == mock_usage
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_claude_sends_the_real_bearer_token(tmp_path):
    """Regression: the dict-shaped `claudeAiOauth` used to leak into the header."""
    creds_path = make_creds_file(tmp_path)
    mock_scraper = make_mock_scraper(200, {"five_hour": {"utilization": 15.0}})

    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        rows = await fetch_claude_usage("enabled", "https://api.anthropic.com")

    headers = mock_scraper.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == f"Bearer {SAMPLE_TOKEN}"
    assert headers["anthropic-beta"] == "oauth-2025-04-20"
    assert mock_scraper.get.call_args.args[0] == "https://api.anthropic.com/api/oauth/usage"
    assert rows[0].used == 15.0
