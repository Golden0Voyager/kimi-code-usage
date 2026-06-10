import pytest
from unittest.mock import patch, AsyncMock
from kimi_code_usage.providers.openrouter import fetch_openrouter_usage

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_success(monkeypatch):
    # Force language to English for test uniformity
    monkeypatch.setenv("LANG", "en")
    
    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        if "credits" in url:
            cm.status = 200
            async def mock_credits_json():
                return {
                    "data": {
                        "total_credits": 10.0,
                        "total_usage": 4.5
                    }
                }
            cm.json = mock_credits_json
        else:
            cm.status = 200
            async def mock_key_json():
                return {
                    "data": {
                        "label": "my-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "usage_daily": 0.1,
                        "usage_weekly": 0.5,
                        "usage_monthly": 1.5,
                        "rate_limit": {
                            "requests": 10,
                            "interval": "1s"
                        }
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
        assert len(res) == 5
        
        # 1. Account Credits item
        assert res[0].provider == "openrouter"
        assert res[0].label == "Credits"
        assert res[0].used == 4.5
        assert res[0].limit == 10.0
        assert res[0].remaining == 5.5
        assert res[0].percent == 45.0
        assert res[0].unit == "$"

        # 2. Key Usage item
        assert res[1].provider == "openrouter"
        assert res[1].label == "Key Usage"
        assert res[1].used == 2.5
        assert res[1].limit == 5.0
        assert res[1].remaining == 2.5
        assert res[1].percent == 50.0
        assert res[1].unit == "$"

        # 3. Key Name item
        assert res[2].provider == "openrouter"
        assert res[2].label == "Key Name"
        assert res[2].unit == "text"
        assert res[2].text_value == "my-key"

        # 4. Rate Limit item
        assert res[3].provider == "openrouter"
        assert res[3].label == "Rate Limit"
        assert res[3].unit == "text"
        assert res[3].text_value == "10 req/1s"

        # 5. Period Usage item
        assert res[4].provider == "openrouter"
        assert res[4].label == "Usage"
        assert res[4].unit == "text"
        assert res[4].text_value == "Daily: $0.1000 | Weekly: $0.5000 | Monthly: $1.5000"

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_success_zh(monkeypatch):
    # Test Chinese localization
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    
    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        if "credits" in url:
            cm.status = 500
        else:
            cm.status = 200
            async def mock_key_json():
                return {
                    "data": {
                        "label": "my-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "usage_daily": 0.1,
                        "usage_weekly": 0.5,
                        "usage_monthly": 1.5
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
        assert len(res) == 3
        assert res[0].label == "Credits"
        assert res[1].label == "Key Name"
        assert res[2].label == "周期已用"
        assert res[2].text_value == "今日: $0.1000 | 本周: $0.5000 | 本月: $1.5000"

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_credits_failed_fallback(monkeypatch):
    monkeypatch.setenv("LANG", "en")
    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        if "credits" in url:
            cm.status = 500
        else:
            cm.status = 200
            async def mock_key_json():
                return {
                    "data": {
                        "label": "unlimited-key",
                        "usage": 2.5,
                        "limit": None
                    }
                }
            cm.json = mock_key_json
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api/v1")
        assert len(res) == 3
        assert res[0].label == "Credits"
        assert res[0].used == 2.5
        assert res[1].label == "Key Name"
        assert res[2].label == "Usage"
        assert res[2].text_value == "Daily: $0.0000 | Weekly: $0.0000 | Monthly: $0.0000"

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_api_error():
    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        if "credits" in url:
            cm.status = 200
            async def mock_credits_json():
                return {"data": {"total_credits": 10.0, "total_usage": 4.5}}
            cm.json = mock_credits_json
        else:
            cm.status = 401
            cm.text = AsyncMock(return_value="Unauthorized")
        return cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_openrouter_usage("bad-key", "https://openrouter.ai/api")
        assert "OpenRouter API Error 401" in str(exc.value)

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_rate_limit_ignored_if_negative_or_missing(monkeypatch):
    monkeypatch.setenv("LANG", "en")
    def mock_get(url, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        if "credits" in url:
            cm.status = 500
        else:
            cm.status = 200
            async def mock_key_json():
                return {
                    "data": {
                        "label": "my-key",
                        "usage": 2.5,
                        "limit": 5.0,
                        "rate_limit": {
                            "requests": -1,
                            "interval": "10s"
                        }
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
        assert len(res) == 3
        assert res[0].label == "Credits"
        assert res[1].label == "Key Name"
        assert res[2].label == "Usage"

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_credits_raises_exception(monkeypatch):
    monkeypatch.setenv("LANG", "en")
    def mock_get(url, *args, **kwargs):
        if "credits" in url:
            raise Exception("Connection timeout")
        
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = 200
        async def mock_key_json():
            return {
                "data": {
                    "label": "my-key",
                    "usage": 2.5,
                    "limit": 5.0
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
        assert len(res) == 3
        assert res[0].label == "Credits"
        assert res[0].used == 2.5
        assert res[0].limit == 5.0
        assert res[1].label == "Key Name"
        assert res[1].text_value == "my-key"
        assert res[2].label == "Usage"



