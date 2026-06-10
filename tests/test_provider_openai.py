import pytest
from unittest.mock import patch, AsyncMock
from kimi_code_usage.providers.openai import fetch_openai_usage

@pytest.mark.asyncio
async def test_fetch_openai_usage_success():
    # Mock completions and costs responses
    async def mock_json_completions(*args, **kwargs):
        return {
            "data": [
                {"input_tokens": 1000, "output_tokens": 500},
                {"input_tokens": 2000, "output_tokens": 1000}
            ]
        }

    async def mock_json_costs(*args, **kwargs):
        return {
            "data": [
                {"amount": {"value": 1.25}},
                {"amount": {"value": 0.75}}
            ]
        }

    def make_mock_cm(status, json_data):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = status
        cm.json = AsyncMock(side_effect=json_data)
        return cm

    mock_session = AsyncMock()
    call_count = [0]
    
    def mock_get(url, **kwargs):
        call_count[0] += 1
        if "completions" in url:
            return make_mock_cm(200, mock_json_completions)
        else:
            return make_mock_cm(200, mock_json_costs)

    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openai_usage("org-admin-key", "https://api.openai.com")
        assert len(res) == 2
        
        # Tokens ProviderUsage
        assert res[0].provider == "openai"
        assert res[0].label == "Tokens"
        assert res[0].used == 4500.0
        assert res[0].limit is None
        assert res[0].unit == "tokens"
        
        # Cost ProviderUsage
        assert res[1].provider == "openai"
        assert res[1].label == "Cost"
        assert res[1].used == 2.0
        assert res[1].unit == "$"

@pytest.mark.asyncio
async def test_fetch_openai_usage_costs_fails_gracefully():
    # If costs endpoint fails, cost should be 0.0, tokens should still succeed
    async def mock_json_completions(*args, **kwargs):
        return {"data": [{"input_tokens": 100, "output_tokens": 50}]}

    def make_mock_cm(status, json_data=None):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = status
        if json_data:
            cm.json = AsyncMock(side_effect=json_data)
        return cm

    mock_session = AsyncMock()
    
    def mock_get(url, **kwargs):
        if "completions" in url:
            return make_mock_cm(200, mock_json_completions)
        else:
            # raise exception to trigger the try-except fallback block
            raise ValueError("Connection failed")

    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        res = await fetch_openai_usage("org-admin-key", "https://api.openai.com")
        assert len(res) == 2
        assert res[0].used == 150.0
        assert res[1].used == 0.0

@pytest.mark.asyncio
async def test_fetch_openai_usage_requires_org_admin():
    # If API key is not org admin, completions endpoint returns 403
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 403

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_openai_usage("regular-key", "https://api.openai.com")
        assert "Requires Org Admin Key" in str(exc.value)

@pytest.mark.asyncio
async def test_fetch_openai_usage_api_error():
    # Other API errors
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 502
    cm.text = AsyncMock(return_value="Bad Gateway")

    mock_session = AsyncMock()
    mock_session.get = lambda *args, **kwargs: cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_openai_usage("key", "https://api.openai.com")
        assert "OpenAI API Error 502" in str(exc.value)
