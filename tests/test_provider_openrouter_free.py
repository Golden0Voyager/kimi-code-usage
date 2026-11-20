"""Free-model daily quota row for the OpenRouter provider.

The asyncio mark is applied module-wide so no per-test decorator is needed.
"""

from unittest.mock import AsyncMock, patch

import pytest

from kimi_code_usage.providers.openrouter import fetch_openrouter_usage

pytestmark = pytest.mark.asyncio


def _json_cm(status, payload):
    """Return a mock async context manager with a json() coroutine."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = status

    async def _json():
        return payload

    cm.json = _json
    return cm


def _make_session(get_handler):
    """Build a mock aiohttp ClientSession driven by get_handler(url, cm, kwargs)."""

    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        get_handler(url, cm, kwargs)
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


async def _run_fetch(monkeypatch, get_handler):
    mock_session = _make_session(get_handler)
    with patch("aiohttp.ClientSession", return_value=mock_session):
        return await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")


def _handler_with_free_quota(free_quota):
    """Route /auth/key to a payload carrying the given free_model_daily_requests."""

    def get_handler(url, cm, kwargs):
        cm.status = 200
        if "credits" in url:
            cm.status = 500
        else:
            payload = {
                "data": {
                    "usage": 2.5,
                    "limit": None,
                    "free_model_daily_requests": free_quota,
                }
            }

            async def _json():
                return payload

            cm.json = _json

    return get_handler


async def test_free_models_row_en(monkeypatch):
    monkeypatch.setenv("LANG", "en")
    res = await _run_fetch(
        monkeypatch, _handler_with_free_quota({"used": 321, "limit": 1000, "remaining": 679})
    )
    row = next(r for r in res if r.label == "Free Models")
    assert row.unit == "text"
    assert row.text_value == "679/1000 free requests left today (resets at UTC 0)"


async def test_free_models_row_zh(monkeypatch):
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    res = await _run_fetch(
        monkeypatch, _handler_with_free_quota({"used": 321, "limit": 1000, "remaining": 679})
    )
    row = next(r for r in res if r.label == "免费模型")
    assert row.text_value == "今日剩余 679/1000 次（UTC 0 点重置）"


async def test_free_models_remaining_computed_when_absent(monkeypatch):
    monkeypatch.setenv("LANG", "en")
    res = await _run_fetch(monkeypatch, _handler_with_free_quota({"used": 40, "limit": 50}))
    row = next(r for r in res if r.label == "Free Models")
    assert row.text_value == "10/50 free requests left today (resets at UTC 0)"


async def test_free_models_remaining_clamped_at_zero(monkeypatch):
    monkeypatch.setenv("LANG", "en")
    res = await _run_fetch(
        monkeypatch, _handler_with_free_quota({"used": 1008, "limit": 1000})
    )
    row = next(r for r in res if r.label == "Free Models")
    assert row.text_value == "0/1000 free requests left today (resets at UTC 0)"


@pytest.mark.parametrize(
    "free_quota",
    [
        None,
        "1000",
        {"used": 10},
        {"limit": 1000},
        {"used": "10", "limit": 1000},
    ],
)
async def test_free_models_row_omitted_for_incomplete_data(monkeypatch, free_quota):
    monkeypatch.setenv("LANG", "en")
    res = await _run_fetch(monkeypatch, _handler_with_free_quota(free_quota))
    assert all(r.label != "Free Models" for r in res)
