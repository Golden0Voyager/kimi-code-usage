import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from kimi_code_usage.config import AppConfig, ProviderConfig
from kimi_code_usage.providers import dispatch_all, ProviderUsage

@pytest.mark.asyncio
async def test_dispatch_all_empty():
    config = AppConfig()
    results, errors = await dispatch_all(config)
    assert len(results) == 0
    assert len(errors) == 0

@pytest.mark.asyncio
async def test_dispatch_all_success():
    config = AppConfig(
        providers={
            "kimi": ProviderConfig(api_key="kimi-key", base_url="https://api.kimi.com/coding/v1"),
            "openai": ProviderConfig(api_key="openai-key", base_url="https://api.openai.com")
        }
    )
    
    mock_kimi_usage = [ProviderUsage(provider="kimi", label="W", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    mock_openai_usage = [ProviderUsage(provider="openai", label="Cost", used=1.5, limit=5.0, remaining=3.5, percent=30, reset_at=None, unit="$")]
    
    with patch("kimi_code_usage.providers.kimi.fetch_kimi_usage", AsyncMock(return_value=mock_kimi_usage)) as mock_kimi, \
         patch("kimi_code_usage.providers.openai.fetch_openai_usage", AsyncMock(return_value=mock_openai_usage)) as mock_openai, \
         patch("kimi_code_usage.providers.anthropic.fetch_anthropic_usage", AsyncMock()) as mock_anthropic, \
         patch("kimi_code_usage.providers.openrouter.fetch_openrouter_usage", AsyncMock()) as mock_openrouter:
         
        results, errors = await dispatch_all(config)
        
        mock_kimi.assert_called_once_with("kimi-key", "https://api.kimi.com/coding/v1")
        mock_openai.assert_called_once_with("openai-key", "https://api.openai.com")
        mock_anthropic.assert_not_called()
        mock_openrouter.assert_not_called()
        
        assert len(errors) == 0
        assert results["kimi"] == mock_kimi_usage
        assert results["openai"] == mock_openai_usage

@pytest.mark.asyncio
async def test_dispatch_all_with_errors_and_timeout():
    config = AppConfig(
        providers={
            "kimi": ProviderConfig(api_key="kimi-key", base_url="https://api.kimi.com/coding/v1"),
            "openai": ProviderConfig(api_key="openai-key", base_url="https://api.openai.com"),
            "anthropic": ProviderConfig(api_key="anthropic-key", base_url="https://api.anthropic.com")
        }
    )
    
    mock_kimi_usage = [ProviderUsage(provider="kimi", label="W", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]

    with patch("kimi_code_usage.providers.kimi.fetch_kimi_usage", AsyncMock(return_value=mock_kimi_usage)), \
         patch("kimi_code_usage.providers.openai.fetch_openai_usage", AsyncMock(side_effect=ValueError("Auth failed"))), \
         patch("kimi_code_usage.providers.anthropic.fetch_anthropic_usage", AsyncMock(side_effect=asyncio.TimeoutError)), \
         patch("kimi_code_usage.providers.openrouter.fetch_openrouter_usage", AsyncMock()):
         
        results, errors = await dispatch_all(config)
        
        assert "kimi" in results
        assert results["kimi"] == mock_kimi_usage
        assert "openai" not in results
        assert "anthropic" not in results
        
        assert errors["openai"] == "Auth failed"
        assert errors["anthropic"] == "Request timed out"

@pytest.mark.asyncio
async def test_dispatch_all_not_configured_or_unknown():
    config = AppConfig(
        providers={
            "kimi": ProviderConfig(api_key=None, base_url="https://api.kimi.com/coding/v1")
        }
    )
    
    with patch.object(AppConfig, "enabled_providers", ["kimi", "unknown"]):
        results, errors = await dispatch_all(config)
        assert "kimi" not in results
        assert errors["kimi"] == "Not configured"
        assert errors["unknown"] == "Unknown provider unknown"


@pytest.mark.asyncio
async def test_dispatch_all_returns_none():
    config = AppConfig(
        providers={
            "kimi": ProviderConfig(api_key="kimi-key", base_url="https://api.kimi.com/coding/v1")
        }
    )
    with patch("kimi_code_usage.providers.kimi.fetch_kimi_usage", AsyncMock(return_value=None)):
        results, errors = await dispatch_all(config)
        assert "kimi" not in results
        assert len(errors) == 0
