from unittest.mock import AsyncMock, patch

import pytest

from kimi_code_usage.providers.anthropic import fetch_anthropic_usage


@pytest.mark.asyncio
async def test_fetch_anthropic_usage_regular_key():
    # If starting with sk-ant-, it should fast-fallback
    res = await fetch_anthropic_usage("sk-ant-api03-xxxx", "https://api.anthropic.com")
    assert len(res) == 1
    assert res[0].provider == "anthropic"
    assert res[0].label == "API Plan"
    assert res[0].used == 0.0

@pytest.mark.asyncio
async def test_fetch_anthropic_usage_oauth_success():
    async def mock_json_oauth(*args, **kwargs):
        return {
            "five_hour": {"utilization": 0.45},
            "seven_day": {"utilization": 0.12}
        }

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = mock_json_oauth

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_anthropic_usage("oauth-token", "https://api.anthropic.com")
        assert len(res) == 2

        assert res[0].label == "5 Hours"
        assert res[0].used == 45.0
        assert res[0].remaining == 55.0
        assert res[0].percent == 45.0
        assert res[0].unit == "%"

        assert res[1].label == "7 Days"
        assert res[1].used == 12.0
        assert res[1].remaining == 88.0
        assert res[1].percent == 12.0
        assert res[1].unit == "%"

@pytest.mark.asyncio
async def test_fetch_anthropic_usage_oauth_auth_error():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 403

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_anthropic_usage("invalid-oauth-token", "https://api.anthropic.com")
        assert len(res) == 1
        assert "API Plan" in res[0].label

@pytest.mark.asyncio
async def test_fetch_anthropic_usage_oauth_api_error():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 500
    cm.text = AsyncMock(return_value="Internal server error")

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_anthropic_usage("oauth-token", "https://api.anthropic.com")
        assert "Anthropic API Error 500" in str(exc.value)
