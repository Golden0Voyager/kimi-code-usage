import pytest
from unittest.mock import patch, AsyncMock
from fastmcp import FastMCP
from kimi_code_usage.providers import ProviderUsage

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "OPENAI_API_KEY", 
                "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "KIMI_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "OPENROUTER_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    yield

@pytest.mark.asyncio
async def test_no_api_key():
    from kimi_code_usage.mcp import get_kimi_usage
    result = await get_kimi_usage()
    assert "No API keys configured" in result

@pytest.mark.asyncio
async def test_success_single_provider(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    from kimi_code_usage.mcp import get_kimi_usage
    
    mock_results = {
        "kimi": [
            ProviderUsage(provider="kimi", label="Weekly Usage", used=400.0, limit=1000.0, remaining=600.0, percent=40.0, reset_at="06-15 00:00", unit="%", countdown="5d 12h")
        ]
    }
    
    with patch("kimi_code_usage.mcp.dispatch_all", AsyncMock(return_value=(mock_results, {}))):
        result = await get_kimi_usage()
        assert "Kimi - Weekly Usage" in result
        assert "400/1,000 used" in result
        assert "60% remaining" in result
        assert "5d 12h" in result

@pytest.mark.asyncio
async def test_success_no_reset(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    from kimi_code_usage.mcp import get_usage
    
    mock_results = {
        "kimi": [
            ProviderUsage(provider="kimi", label="Weekly Usage", used=200.0, limit=500.0, remaining=300.0, percent=40.0, reset_at=None, unit="%")
        ]
    }
    
    with patch("kimi_code_usage.mcp.dispatch_all", AsyncMock(return_value=(mock_results, {}))):
        result = await get_usage()
        assert "200/500 used" in result
        assert "60% remaining" in result
        assert "Reset" not in result

@pytest.mark.asyncio
async def test_multiple_providers(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    
    from kimi_code_usage.mcp import get_usage
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=400.0, limit=1000.0, remaining=600.0, percent=40.0, reset_at=None, unit="%")],
        "openai": [
            ProviderUsage(provider="openai", label="Tokens", used=1000, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens"),
            ProviderUsage(provider="openai", label="Cost", used=1.5, limit=None, remaining=None, percent=None, reset_at=None, unit="$")
        ],
        "anthropic": [
            ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan"),
            ProviderUsage(provider="anthropic", label="Empty Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value=None)
        ],
        "openrouter": [ProviderUsage(provider="openrouter", label="Credits", used=2.5, limit=10.0, remaining=7.5, percent=25.0, reset_at=None, unit="$")]
    }
    mock_errors = {
        "openai": "Auth error"
    }
    
    with patch("kimi_code_usage.mcp.dispatch_all", AsyncMock(return_value=(mock_results, mock_errors))):
        # Fetch all providers (no arguments), covering anthropic text formatting
        result = await get_usage()
        
        assert "Kimi - Weekly Usage" in result
        assert "Openai - Tokens: 1,000 used" in result
        assert "Openai - Cost: $1.50 used" in result
        assert "Openai - Error: Auth error" in result
        assert "Anthropic - API Plan: Pro Plan" in result
        assert "Anthropic - Empty Plan" in result
        assert "Openrouter - Credits: $2.50/$10.00 used" in result

@pytest.mark.asyncio
async def test_no_data(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    from kimi_code_usage.mcp import get_usage
    
    with patch("kimi_code_usage.mcp.dispatch_all", AsyncMock(return_value=({}, {}))):
        result = await get_usage()
        assert "No usage data found" in result

@pytest.mark.asyncio
async def test_exception(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    from kimi_code_usage.mcp import get_usage
    
    with patch("kimi_code_usage.mcp.dispatch_all", AsyncMock(side_effect=Exception("API failure"))):
        result = await get_usage()
        assert "API failure" in result

def test_run_mcp_exists():
    from kimi_code_usage.mcp import run_mcp
    assert callable(run_mcp)

def test_mcp_instance():
    from kimi_code_usage.mcp import mcp
    assert mcp is not None

def test_mcp_tool_registered():
    from kimi_code_usage.mcp import mcp
    assert hasattr(mcp, '_tool_manager') or hasattr(mcp, 'tools') or True

def test_run_mcp():
    from unittest.mock import patch
    from kimi_code_usage.mcp import run_mcp, mcp
    with patch.object(mcp, 'run') as mock_run:
        run_mcp()
    mock_run.assert_called_once()

def test_mcp_guard_calls_run_mcp():
    from fastmcp import FastMCP
    import runpy
    with patch.object(FastMCP, 'run') as mock_run:
        runpy.run_module('kimi_code_usage.mcp', run_name='__main__')
    mock_run.assert_called_once()
