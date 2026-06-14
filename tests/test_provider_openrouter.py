import pytest
from unittest.mock import patch, AsyncMock
from kimi_code_usage.providers.openrouter import (
    fetch_openrouter_usage,
    _build_activity,
    _build_daily_activity,
    _model_short_name,
)


def _json_cm(status, payload):
    """Return a mock async context manager with a json() coroutine."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = status
    if callable(payload):
        cm.json = payload
    elif isinstance(payload, Exception):
        cm.text = AsyncMock(return_value=str(payload))
    else:
        async def _json():
            return payload
        cm.json = _json
    return cm


def _make_session(get_handler):
    """Build a mock aiohttp ClientSession driven by get_handler(url, kwargs)."""
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


async def _run_fetch(monkeypatch, get_handler, api_key="or-key", base_url="https://openrouter.ai/api", management_key=None):
    mock_session = _make_session(get_handler)
    with patch("aiohttp.ClientSession", return_value=mock_session):
        return await fetch_openrouter_usage(api_key, base_url, management_key=management_key)


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_success(monkeypatch):
    # Force language to English for test uniformity
    monkeypatch.setenv("LANG", "en")
    
    def get_handler(url, cm, kwargs):
        if "credits" in url:
            async def mock_credits_json():
                return {"data": {"total_credits": 10.0, "total_usage": 4.5}}
            cm.status = 200
            cm.json = mock_credits_json
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "my-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "usage_daily": 0.1,
                        "usage_weekly": 0.5,
                        "usage_monthly": 1.5,
                        "rate_limit": {"requests": 10, "interval": "1s"},
                    }
                }
            cm.status = 200
            cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler)
    assert len(res) == 5

    assert res[0].provider == "openrouter"
    assert res[0].label == "Credits"
    assert res[0].used == 4.5
    assert res[0].limit == 10.0
    assert res[0].remaining == 5.5
    assert res[0].percent == 45.0
    assert res[0].unit == "$"

    assert res[1].provider == "openrouter"
    assert res[1].label == "Key Usage"
    assert res[1].used == 2.5
    assert res[1].limit == 5.0
    assert res[1].remaining == 2.5
    assert res[1].percent == 50.0
    assert res[1].unit == "$"

    assert res[2].provider == "openrouter"
    assert res[2].label == "Key Name"
    assert res[2].unit == "text"
    assert res[2].text_value == "my-key"

    assert res[3].provider == "openrouter"
    assert res[3].label == "Rate Limit"
    assert res[3].unit == "text"
    assert res[3].text_value == "10 req/1s"

    assert res[4].provider == "openrouter"
    assert res[4].label == "Usage"
    assert res[4].unit == "text"
    assert res[4].text_value == "Daily: $0.1000 | Weekly: $0.5000 | Monthly: $1.5000"


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_success_zh(monkeypatch):
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")

    def get_handler(url, cm, kwargs):
        if "credits" in url:
            cm.status = 500
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "my-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "usage_daily": 0.1,
                        "usage_weekly": 0.5,
                        "usage_monthly": 1.5,
                    }
                }
            cm.status = 200
            cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler)
    assert len(res) == 3
    assert res[0].label == "Credits"
    assert res[1].label == "Key Name"
    assert res[2].label == "周期已用"
    assert res[2].text_value == "今日: $0.1000 | 本周: $0.5000 | 本月: $1.5000"

@pytest.mark.parametrize("requests_val,interval,lang,expected_text", [
    (20, "10s", "zh_CN.UTF-8", "20次/10秒"),
    (-1, "1m", "zh_CN.UTF-8", "无限制/1分钟"),
    (-1, "10s", "en", "Unlimited/10s"),
])
@pytest.mark.asyncio
async def test_fetch_openrouter_usage_rate_limit(monkeypatch, requests_val, interval, lang, expected_text):
    monkeypatch.setenv("LANG", lang)

    def get_handler(url, cm, kwargs):
        if "credits" in url:
            cm.status = 500
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "my-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "rate_limit": {"requests": requests_val, "interval": interval},
                    }
                }
            cm.status = 200
            cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler)
    assert len(res) == 4
    assert res[2].label in ("Rate Limit", "速率限制")
    assert res[2].text_value == expected_text


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_credits_failed_fallback(monkeypatch):
    def get_handler(url, cm, kwargs):
        if "credits" in url:
            cm.status = 500
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "sk-or-v1-276...eab",
                        "usage": 2.5,
                        "limit": None,
                        "is_management_key": True,
                    }
                }
            cm.status = 200
            cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler, base_url="https://openrouter.ai/api/v1")
    assert len(res) == 3
    assert res[0].label == "Credits"
    assert res[0].used == 2.5
    assert res[1].label == "Management Key"
    assert res[1].text_value == "sk-or-v1-276*********eab"
    assert res[2].label == "Usage"
    assert res[2].text_value == "Daily: $0.0000 | Weekly: $0.0000 | Monthly: $0.0000"


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_api_error():
    def get_handler(url, cm, kwargs):
        if "credits" in url:
            cm.status = 200
            async def mock_credits_json():
                return {"data": {"total_credits": 10.0, "total_usage": 4.5}}
            cm.json = mock_credits_json
        else:
            cm.status = 401
            cm.text = AsyncMock(return_value="Unauthorized")

    with pytest.raises(Exception) as exc:
        await _run_fetch(None, get_handler, api_key="bad-key")
    assert "OpenRouter API Error 401" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_credits_raises_exception(monkeypatch):
    def get_handler(url, cm, kwargs):
        if "credits" in url:
            raise Exception("Connection timeout")
        cm.status = 200
        async def mock_key_json():
            return {"data": {"label": "my-key", "usage": 2.5, "limit": 5.0}}
        cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler)
    assert len(res) == 3
    assert res[0].label == "Credits"
    assert res[0].used == 2.5
    assert res[0].limit == 5.0
    assert res[1].label == "Key Name"
    assert res[1].text_value == "my-key"
    assert res[2].label == "Usage"


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_edge_cases(monkeypatch):
    def get_handler(url, cm, kwargs):
        cm.status = 200
        if "credits" in url:
            async def mock_credits_json():
                return {"data": {"total_usage": 1.5}}
            cm.json = mock_credits_json
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "usage": 2.5,
                        "limit": 5.0,
                        "rate_limit": "not-a-dict",
                    }
                }
            cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler)
    assert len(res) == 2
    assert res[0].label == "Credits"
    assert res[0].used == 2.5
    assert res[0].limit == 5.0


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_extra_metadata(monkeypatch):
    def get_handler(url, cm, kwargs):
        cm.status = 200
        if "credits" in url:
            async def mock_credits_json():
                return {"data": {"total_credits": 10.0, "total_usage": 4.5}}
            cm.json = mock_credits_json
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "meta-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "is_free_tier": True,
                        "limit_reset": "monthly",
                        "expires_at": "2026-06-12T12:00:00Z",
                        "is_provisioning_key": False,
                    }
                }
            cm.json = mock_key_json

    res = await _run_fetch(monkeypatch, get_handler)
    assert len(res) == 7
    assert res[3].label == "Free Tier"
    assert res[3].text_value == "Yes"
    assert res[4].label == "Limit Reset"
    assert res[4].text_value == "monthly"
    assert res[5].label == "Expires At"
    assert res[5].text_value == "2026-06-12T12:00:00Z"
    assert res[6].label == "Usage"


def test_build_activity():
    items = [
        {
            "date": "2026-06-10",
            "model": "anthropic/claude-opus-4",
            "usage": 1.5,
            "requests": 10,
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "reasoning_tokens": 100,
        },
        {
            "date": "2026-06-10",
            "model": "openai/gpt-4.1",
            "usage": 0.8,
            "requests": 20,
            "prompt_tokens": 2000,
            "completion_tokens": 800,
            "reasoning_tokens": 0,
        },
        {
            "date": "2026-06-11",
            "model": "anthropic/claude-opus-4",
            "usage": 2.0,
            "requests": 15,
            "prompt_tokens": 1500,
            "completion_tokens": 700,
            "reasoning_tokens": 200,
        },
    ]
    totals, models = _build_activity(items)
    assert totals.spend == 4.3
    assert totals.requests == 45
    assert totals.prompt_tokens == 4500
    assert totals.completion_tokens == 2000
    assert totals.reasoning_tokens == 300

    assert len(models) == 2
    assert models[0].model == "anthropic/claude-opus-4"
    assert models[0].spend == 3.5
    assert models[1].model == "openai/gpt-4.1"
    assert models[1].spend == 0.8


def test_build_daily_activity():
    items = [
        {"date": "2026-06-10", "model": "anthropic/claude-opus-4", "usage": 1.5, "requests": 10},
        {"date": "2026-06-10", "model": "openai/gpt-4.1", "usage": 0.8, "requests": 20},
        {"date": "2026-06-11", "model": "anthropic/claude-opus-4", "usage": 2.0, "requests": 15},
        {"date": "", "model": "skipped", "usage": 1.0, "requests": 1},
    ]
    daily = _build_daily_activity(items)
    assert len(daily) == 2
    assert daily[0].date == "2026-06-10"
    assert daily[0].total == 2.3
    assert len(daily[0].models) == 2
    assert daily[1].date == "2026-06-11"
    assert daily[1].total == 2.0


def test_model_short_name():
    assert _model_short_name("anthropic/claude-opus-4") == "claude-opus-4"
    assert _model_short_name("gpt-4o") == "gpt-4o"


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_management_key_with_activity(monkeypatch):
    monkeypatch.setenv("LANG", "en")

    activity_calls = []

    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = 200

        if "credits" in url:
            async def mock_credits_json():
                return {"data": {"total_credits": 100.0, "total_usage": 10.0}}
            cm.json = mock_credits_json
        elif "activity" in url:
            activity_calls.append(url)
            async def mock_activity_json():
                return {
                    "data": [
                        {
                            "date": "2026-06-10",
                            "model": "anthropic/claude-opus-4",
                            "usage": 1.5,
                            "requests": 10,
                            "prompt_tokens": 1000,
                            "completion_tokens": 500,
                            "reasoning_tokens": 100,
                        },
                        {
                            "date": "2026-06-11",
                            "model": "openai/gpt-4.1",
                            "usage": 0.8,
                            "requests": 20,
                            "prompt_tokens": 2000,
                            "completion_tokens": 800,
                        },
                    ]
                }
            cm.json = mock_activity_json
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "mgmt-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "is_management_key": True,
                        "usage_daily": 0.1,
                        "usage_weekly": 0.5,
                        "usage_monthly": 1.5,
                    }
                }
            cm.json = mock_key_json
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")

    assert len(activity_calls) == 1
    activity_item = next(r for r in res if r.label == "Activity")
    assert activity_item is not None
    assert activity_item.activity_totals.requests == 30
    assert activity_item.activity_totals.spend == 2.3

    daily_item = next(r for r in res if r.label == "Daily Spend")
    assert daily_item is not None
    assert len(daily_item.daily_activity) == 2

    top_item = next(r for r in res if r.label == "Top Models")
    assert top_item is not None
    assert len(top_item.top_models) == 2


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_standard_key_no_activity(monkeypatch):
    monkeypatch.setenv("LANG", "en")

    activity_calls = []

    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = 200

        if "credits" in url:
            async def mock_credits_json():
                return {"data": {"total_credits": 100.0, "total_usage": 10.0}}
            cm.json = mock_credits_json
        elif "activity" in url:
            activity_calls.append(url)
            async def mock_activity_json():
                return {"data": []}
            cm.json = mock_activity_json
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "std-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "is_management_key": False,
                    }
                }
            cm.json = mock_key_json
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")

        assert len(activity_calls) == 1
    assert not any(r.label in ("Activity", "Daily Spend", "Top Models") for r in res)


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_activity_request_exception(monkeypatch):
    """If /activity request raises, it should be silently ignored."""
    monkeypatch.setenv("LANG", "en")

    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)

        if "credits" in url:
            cm.status = 200
            async def mock_credits_json():
                return {"data": {"total_credits": 100.0, "total_usage": 10.0}}
            cm.json = mock_credits_json
        elif "activity" in url:
            raise RuntimeError("network down")
        else:
            cm.status = 200
            async def mock_key_json():
                return {
                    "data": {
                        "label": "test-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "is_management_key": True,
                    }
                }
            cm.json = mock_key_json
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")

    assert any(r.label == "Credits" for r in res)
    assert not any(r.label in ("Activity", "Daily Spend", "Top Models") for r in res)


@pytest.mark.asyncio
async def test_fetch_openrouter_usage_management_key_separate_from_api_key(monkeypatch):
    """If management_key is provided, activity endpoint should use it, key/credits use api_key."""
    monkeypatch.setenv("LANG", "en")

    calls = []

    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = 200
        auth = kwargs.get("headers", {}).get("Authorization", "")
        calls.append((url, auth))

        if "credits" in url:
            async def mock_credits_json():
                return {"data": {"total_credits": 100.0, "total_usage": 10.0}}
            cm.json = mock_credits_json
        elif "activity" in url:
            async def mock_activity_json():
                return {
                    "data": [
                        {
                            "date": "2026-06-11",
                            "model": "anthropic/claude-opus-4",
                            "usage": 3.0,
                            "requests": 15,
                            "prompt_tokens": 1500,
                            "completion_tokens": 700,
                        },
                    ]
                }
            cm.json = mock_activity_json
        else:
            async def mock_key_json():
                return {
                    "data": {
                        "label": "std-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "is_management_key": False,
                    }
                }
            cm.json = mock_key_json
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("api-key", "https://openrouter.ai/api", management_key="mgmt-key")

    activity_calls = [(url, auth) for url, auth in calls if "activity" in url]
    key_calls = [(url, auth) for url, auth in calls if "auth/key" in url]
    credits_calls = [(url, auth) for url, auth in calls if "credits" in url]

    assert len(activity_calls) == 1
    assert "mgmt-key" in activity_calls[0][1]
    assert len(key_calls) == 1
    assert "api-key" in key_calls[0][1]
    assert len(credits_calls) == 1
    assert "api-key" in credits_calls[0][1]

    assert any(r.label == "Activity" for r in res)
    assert any(r.label == "Daily Spend" for r in res)
    assert any(r.label == "Top Models" for r in res)



@pytest.mark.asyncio
async def test_fetch_openrouter_usage_activity_endpoint_ignored_on_error(monkeypatch):
    monkeypatch.setenv("LANG", "en")

    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)

        if "credits" in url:
            cm.status = 200
            async def mock_credits_json():
                return {"data": {"total_credits": 100.0, "total_usage": 10.0}}
            cm.json = mock_credits_json
        elif "activity" in url:
            cm.status = 500
            cm.text = AsyncMock(return_value="Internal Server Error")
        else:
            cm.status = 200
            async def mock_key_json():
                return {
                    "data": {
                        "label": "mgmt-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "is_management_key": True,
                    }
                }
            cm.json = mock_key_json
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")

    assert not any(r.label in ("Activity", "Daily Spend", "Top Models") for r in res)



