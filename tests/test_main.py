import json
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock
from rich.text import Text
from kimi_code_usage.providers import ProviderUsage
from kimi_code_usage.main import (
    _get_visual_width,
    _get_localized_label,
    _format_aggregated_results,
    main,
    run_cli,
)

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "OPENAI_API_KEY", 
                "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "KIMI_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "OPENROUTER_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    yield

def test_get_visual_width():
    assert _get_visual_width("hello") == 5
    assert _get_visual_width("你好") == 4
    assert _get_visual_width("a你好b") == 6

def test_get_localized_label():
    assert _get_localized_label("Weekly Usage") == "Weekly Usage" or "周" in _get_localized_label("Weekly Usage")
    assert _get_localized_label("5h Limit") == "5h Limit" or "限额" in _get_localized_label("5h Limit")
    assert _get_localized_label("Other") == "Other"

def test_format_aggregated_results():
    results = {
        "kimi": [
            ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at="06-11 12:00", unit="%", countdown="1d 2h")
        ],
        "openai": [
            ProviderUsage(provider="openai", label="Tokens Limit", used=1500, limit=10000.0, remaining=8500.0, percent=15.0, reset_at=None, unit="tokens"),
            ProviderUsage(provider="openai", label="Tokens No Limit", used=5000, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens"),
            ProviderUsage(provider="openai", label="Cost", used=1.5, limit=5.0, remaining=3.5, percent=30, reset_at=None, unit="$")
        ],
        "anthropic": [
            ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text")
        ],
        "openrouter": [
            ProviderUsage(provider="openrouter", label="Credits", used=2.5, limit=None, remaining=None, percent=None, reset_at=None, unit="$")
        ]
    }
    errors = {
        "openai": "API Key invalid"
    }
    
    text = _format_aggregated_results(results, errors)
    assert isinstance(text, Text)
    raw_text = str(text)
    assert "Kimi" in raw_text
    assert "Openai" in raw_text
    assert "Openrouter" in raw_text
    
    # Check limit-bar format and no limit format
    assert "1,500 / 10,000 tokens" in raw_text
    assert "$1.50" in raw_text
    assert "$2.50" in raw_text
    
    # Check error message
    assert "⚠ API Key invalid" in raw_text

@pytest.mark.asyncio
async def test_main_no_providers_configured(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "--plain"])
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=({}, {}))):
        await main()
    captured = capsys.readouterr()
    assert "No usage data" in captured.out or "未找到" in captured.out

@pytest.mark.asyncio
async def test_main_json_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    }
    mock_errors = {"openai": "Auth failed"}
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, mock_errors))):
        await main()
        
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert "kimi" in data
    assert data["kimi"][0]["used"] == 10
    assert data["errors"]["openai"] == "Auth failed"

@pytest.mark.asyncio
async def test_main_plain_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--plain"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens")],
        "anthropic": [ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text")]
    }
    mock_errors = {"openrouter": "Timeout"}
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, mock_errors))):
        await main()
        
    captured = capsys.readouterr()
    assert "Kimi - " in captured.out
    assert "Openai - Tokens" in captured.out
    assert "Anthropic - API Plan" in captured.out
    assert "Openrouter - Error: Timeout" in captured.err

@pytest.mark.asyncio
async def test_main_rich_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    }
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, {}))):
        await main()
        
    captured = capsys.readouterr()
    assert "Weekly Usage" in captured.out or "周" in captured.out

@pytest.mark.asyncio
async def test_main_with_provider_filter(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setattr("sys.argv", ["prog", "--provider", "kimi", "--plain"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens")]
    }
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, {}))) as mock_dispatch:
        await main()
        mock_dispatch.assert_called_once()
        config = mock_dispatch.call_args[0][0]
        assert config.providers["openai"].api_key is None
        assert config.providers["kimi"].api_key == "kimi-key"
        
    captured = capsys.readouterr()
    assert "Kimi - " in captured.out
    assert "Openai" not in captured.out

@pytest.mark.asyncio
async def test_main_custom_config_path(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "--config", "/tmp/dummy.json"])
    
    with patch("kimi_code_usage.main.ConfigResolver") as mock_resolver:
        mock_resolver.return_value.resolve.return_value.enabled_providers = []
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=({}, {}))):
            await main()
            mock_resolver.assert_called_once_with(config_path="/tmp/dummy.json")

def test_run_cli(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog"])
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=({}, {}))):
        run_cli()

def test_main_guard_calls_run_cli():
    import runpy
    import asyncio
    with patch.object(asyncio, 'run') as mock_run:
        runpy.run_module('kimi_code_usage.main', run_name='__main__')
    mock_run.assert_called_once()
