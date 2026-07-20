"""Tests for the Codex (ChatGPT Plus) provider."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kimi_code_usage.providers import ProviderUsage
from kimi_code_usage.providers.codex import (
    CODEX_AUTH_PATH,
    _parse_usage_response,
    _read_auth,
    _refresh_access_token,
    fetch_codex_usage,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_lang():
    """Ensure LANG stays 'en' during tests."""
    with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=False):
        yield


SAMPLE_AUTH = {
    "auth_mode": "chatgpt",
    "OPENAI_API_KEY": None,
    "tokens": {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "account_id": "test-account-id",
        "id_token": "test-id-token",
    },
}


def make_auth_file(tmp_path: Path, content: dict | None = None) -> Path:
    """Write an auth.json file and return its path."""
    auth_path = tmp_path / "auth.json"
    if content is not None:
        auth_path.write_text(json.dumps(content), encoding="utf-8")
    else:
        auth_path.write_text(json.dumps(SAMPLE_AUTH), encoding="utf-8")
    return auth_path


def make_mock_scraper(status: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Create a mock cloudscraper with a response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    if json_data is not None:
        mock_resp.json.return_value = json_data
    if text:
        mock_resp.text = text
    mock_scraper = MagicMock()
    mock_scraper.get.return_value = mock_resp
    mock_scraper.post.return_value = mock_resp
    return mock_scraper


# ──────────────────────────────────────────────────────────────────────────
# _read_auth
# ──────────────────────────────────────────────────────────────────────────


def test_read_auth_success(tmp_path):
    auth_path = make_auth_file(tmp_path)
    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path):
        result = _read_auth()
    assert result["access_token"] == "test-access-token"
    assert result["account_id"] == "test-account-id"
    assert result["refresh_token"] == "test-refresh-token"


def test_read_auth_not_found(tmp_path):
    auth_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path):
        with pytest.raises(FileNotFoundError, match="Codex auth file not found"):
            _read_auth()


def test_read_auth_bad_json(tmp_path):
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("not json", encoding="utf-8")
    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path):
        with pytest.raises(RuntimeError, match="Failed to read Codex auth file"):
            _read_auth()


def test_read_auth_wrong_mode(tmp_path):
    auth = dict(SAMPLE_AUTH, auth_mode="apikey")
    auth_path = make_auth_file(tmp_path, auth)
    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path):
        with pytest.raises(RuntimeError, match="expected 'chatgpt'"):
            _read_auth()


def test_read_auth_missing_fields(tmp_path):
    auth = {"auth_mode": "chatgpt", "tokens": {}}
    auth_path = make_auth_file(tmp_path, auth)
    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path):
        with pytest.raises(RuntimeError, match="missing 'access_token'"):
            _read_auth()


# ──────────────────────────────────────────────────────────────────────────
# _refresh_access_token
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_access_token_success():
    mock_scraper = make_mock_scraper(200, {"access_token": "new-token", "refresh_token": "new-refresh"})

    with patch("cloudscraper.create_scraper", return_value=mock_scraper):
        result = await _refresh_access_token("old-refresh")

    assert result["access_token"] == "new-token"
    assert result["refresh_token"] == "new-refresh"


@pytest.mark.asyncio
async def test_refresh_access_token_no_new_refresh():
    """If the response omits refresh_token, the old one is preserved."""
    mock_scraper = make_mock_scraper(200, {"access_token": "new-token"})

    with patch("cloudscraper.create_scraper", return_value=mock_scraper):
        result = await _refresh_access_token("old-refresh")

    assert result["access_token"] == "new-token"
    assert result["refresh_token"] == "old-refresh"


@pytest.mark.asyncio
async def test_refresh_access_token_failure():
    mock_scraper = make_mock_scraper(400, text="bad request")

    with patch("cloudscraper.create_scraper", return_value=mock_scraper):
        with pytest.raises(RuntimeError, match="Token refresh failed"):
            await _refresh_access_token("old-refresh")


@pytest.mark.asyncio
async def test_refresh_access_token_missing_access_token():
    mock_scraper = make_mock_scraper(200, {"refresh_token": "new-refresh"})

    with patch("cloudscraper.create_scraper", return_value=mock_scraper):
        with pytest.raises(RuntimeError, match="missing 'access_token'"):
            await _refresh_access_token("old-refresh")


# ──────────────────────────────────────────────────────────────────────────
# _parse_usage_response
# ──────────────────────────────────────────────────────────────────────────


def test_parse_plan():
    """Parse the actual /wham/usage response format."""
    data = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 23,
                "limit_window_seconds": 604800,
                "reset_after_seconds": 525753,
                "reset_at": 1785044789,
            },
            "secondary_window": None,
        },
        "credits": {
            "has_credits": False,
            "unlimited": False,
            "balance": "0",
        },
        "spend_control": {"reached": False, "individual_limit": None},
    }
    rows = _parse_usage_response(data)
    labels = [r.label for r in rows]
    assert "Plan" in labels
    assert "Weekly Usage" in labels
    assert "Credit Balance" in labels
    weekly = [r for r in rows if r.label == "Weekly Usage"][0]
    assert weekly.used == 23.0
    assert weekly.percent == 23.0


def test_parse_plan_zh():
    """Parse with Chinese locale."""
    with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}, clear=False):
        data = {
            "plan_type": "plus",
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {
                    "used_percent": 50,
                    "limit_window_seconds": 604800,
                    "reset_after_seconds": 100000,
                    "reset_at": 1785044789,
                },
            },
        }
        rows = _parse_usage_response(data)
        labels = [r.label for r in rows]
        assert "周用量" in labels


def test_parse_with_secondary_window():
    data = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 20,
                "limit_window_seconds": 604800,
                "reset_after_seconds": 500000,
                "reset_at": 1785044789,
            },
            "secondary_window": {
                "used_percent": 5,
                "limit_window_seconds": 18000,
                "reset_after_seconds": 5000,
                "reset_at": 1784458800,
            },
        },
    }
    rows = _parse_usage_response(data)
    labels = [r.label for r in rows]
    assert "Weekly Usage" in labels
    assert "5h Limit" in labels


def test_parse_fallback_to_raw():
    data = {"unexpected": "format", "other": 123}
    rows = _parse_usage_response(data)
    assert len(rows) == 1
    assert rows[0].unit == "text"
    assert "unexpected" in (rows[0].text_value or "")


# ──────────────────────────────────────────────────────────────────────────
# fetch_codex_usage — integration (mocked)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_success(tmp_path):
    auth_path = make_auth_file(tmp_path)

    usage_data = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 23,
                "limit_window_seconds": 604800,
                "reset_after_seconds": 525753,
                "reset_at": 1785044789,
            },
        },
        "credits": {"has_credits": False, "balance": "0"},
        "spend_control": {"reached": False, "individual_limit": None},
    }

    mock_scraper = make_mock_scraper(200, usage_data)

    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        rows = await fetch_codex_usage("enabled", "https://chatgpt.com/backend-api")

    assert len(rows) == 3  # plan + weekly + credit balance
    assert rows[0].provider == "codex"
    assert rows[0].label == "Plan"
    assert rows[0].text_value == "ChatGPT Plus"
    # Credit balance row
    assert rows[1].label == "Credit Balance"
    # Weekly usage row
    weekly = [r for r in rows if r.label == "Weekly Usage"]
    assert len(weekly) == 1
    assert weekly[0].used == 23.0


@pytest.mark.asyncio
async def test_fetch_api_error(tmp_path):
    auth_path = make_auth_file(tmp_path)

    mock_scraper = make_mock_scraper(500, text="Internal Server Error")

    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path), \
         patch("cloudscraper.create_scraper", return_value=mock_scraper):
        with pytest.raises(RuntimeError, match="Codex API Error"):
            await fetch_codex_usage("enabled", "https://chatgpt.com/backend-api")


@pytest.mark.asyncio
async def test_fetch_auth_file_not_found(tmp_path):
    auth_path = tmp_path / "nonexistent.json"
    with patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path):
        with pytest.raises(FileNotFoundError, match="Codex auth file not found"):
            await fetch_codex_usage("enabled", "https://chatgpt.com/backend-api")


# ──────────────────────────────────────────────────────────────────────────
# dispatch_all integration
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_all_codex_integration(tmp_path):
    """Verify codex is properly wired into dispatch_all."""
    from kimi_code_usage.config import AppConfig, ProviderConfig
    from kimi_code_usage.providers import dispatch_all

    config = AppConfig(
        providers={
            "codex": ProviderConfig(api_key="enabled", base_url="https://chatgpt.com/backend-api", enabled=True),
        }
    )

    mock_usage = [ProviderUsage(provider="codex", label="Plan", used=0.0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="ChatGPT Plus")]

    with patch("kimi_code_usage.providers.codex.fetch_codex_usage", new_callable=AsyncMock, return_value=mock_usage):
        results, errors = await dispatch_all(config)

    assert "codex" in results
    assert results["codex"] == mock_usage
    assert len(errors) == 0