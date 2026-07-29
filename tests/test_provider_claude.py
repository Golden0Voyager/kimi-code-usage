"""Tests for the Claude subscription provider."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kimi_code_usage.providers import ProviderUsage
from kimi_code_usage.providers.claude import (
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


SAMPLE_CREDENTIALS = {"claudeAiOauth": "test-oauth-token"}


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
    creds_path = make_creds_file(tmp_path)
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path):
        token = _read_oauth_token()
    assert token == "test-oauth-token"


def test_read_oauth_token_from_env(tmp_path):
    creds_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.claude.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "env-token"}, clear=False):
        token = _read_oauth_token()
    assert token == "env-token"


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
