import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from kimi_code_usage.config import ConfigResolver, AppConfig

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Completely clear all related environment variables to ensure test isolation
    for key in ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "OPENAI_API_KEY", 
                "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "KIMI_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "OPENROUTER_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    yield

def test_config_resolver_default_not_exist(tmp_path):
    config_path = tmp_path / "nonexistent.json"
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    
    assert isinstance(config, AppConfig)
    assert config.refresh_interval_minutes == 5
    assert config.output_mode == "rich"
    assert len(config.enabled_providers) == 0

def test_config_resolver_invalid_json(tmp_path):
    config_path = tmp_path / "invalid.json"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write("not-json")
        
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert config.refresh_interval_minutes == 5
    assert len(config.enabled_providers) == 0

def test_config_resolver_valid_json(tmp_path):
    config_path = tmp_path / "valid.json"
    data = {
        "providers": {
            "kimi": { "apiKey": "kimi-key", "baseUrl": "https://custom.kimi" },
            "openai": { "apiKey": "openai-key" }
        },
        "general": {
            "refreshIntervalMinutes": 10,
            "outputMode": "plain"
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    
    assert config.refresh_interval_minutes == 10
    assert config.output_mode == "plain"
    assert "kimi" in config.enabled_providers
    assert "openai" in config.enabled_providers
    assert "anthropic" not in config.enabled_providers
    
    assert config.providers["kimi"].api_key == "kimi-key"
    assert config.providers["kimi"].base_url == "https://custom.kimi"
    assert config.providers["openai"].api_key == "openai-key"
    assert config.providers["openai"].base_url == "https://api.openai.com"

def test_config_resolver_env_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "env-kimi-key")
    monkeypatch.setenv("KIMI_BASE_URL", "https://env.kimi")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic-key")
    
    config_path = tmp_path / "nonexistent.json"
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    
    assert "kimi" in config.enabled_providers
    assert "anthropic" in config.enabled_providers
    assert "openai" not in config.enabled_providers
    assert "openrouter" not in config.enabled_providers
    
    assert config.providers["kimi"].api_key == "env-kimi-key"
    assert config.providers["kimi"].base_url == "https://env.kimi"
    assert config.providers["anthropic"].api_key == "env-anthropic-key"
    assert config.providers["anthropic"].base_url == "https://api.anthropic.com"

def test_config_resolver_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-env-key")
    
    config_path = tmp_path / "config.json"
    data = {
        "providers": {
            "kimi": { "apiKey": "kimi-json-key" }
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    
    assert config.providers["kimi"].api_key == "kimi-json-key"

def test_config_resolver_no_arg(tmp_path):
    dummy_path = tmp_path / "dummy_default.json"
    with patch("kimi_code_usage.config.DEFAULT_CONFIG_PATH", dummy_path):
        resolver = ConfigResolver()
        assert resolver.config_path == dummy_path
