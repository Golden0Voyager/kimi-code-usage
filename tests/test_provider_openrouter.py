import pytest
from unittest.mock import patch, AsyncMock
from kimi_code_usage.providers.openrouter import fetch_openrouter_usage

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_success():
    async def mock_json_openrouter(*args, **kwargs):
        return {
            "data": {
                "label": "my-key",
                "usage": 4.5,
                "limit": 10.0,
                "is_free": False
            }
        }

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = mock_json_openrouter

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")
        assert len(res) == 1
        
        assert res[0].provider == "openrouter"
        assert res[0].label == "Credits"
        assert res[0].used == 4.5
        assert res[0].limit == 10.0
        assert res[0].remaining == 5.5
        assert res[0].percent == 45.0
        assert res[0].unit == "$"

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_no_limit():
    async def mock_json_openrouter(*args, **kwargs):
        return {
            "data": {
                "label": "unlimited-key",
                "usage": 2.5,
                "limit": None
            }
        }

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = mock_json_openrouter

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openrouter_usage("or-key", "https://openrouter.ai/api")
        assert len(res) == 1
        assert res[0].used == 2.5
        assert res[0].limit is None
        assert res[0].remaining is None
        assert res[0].percent is None

@pytest.mark.asyncio
async def test_fetch_openrouter_usage_api_error():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 401
    cm.text = AsyncMock(return_value="Unauthorized")

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_openrouter_usage("bad-key", "https://openrouter.ai/api")
        assert "OpenRouter API Error 401" in str(exc.value)
