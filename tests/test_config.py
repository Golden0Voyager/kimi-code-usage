import json
from unittest.mock import patch

import pytest

from kimi_code_usage.config import AppConfig, ConfigResolver


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Completely clear all related environment variables to ensure test isolation
    for key in ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_ADMIN_KEY",
                "OPENROUTER_MANAGEMENT_KEY",
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

def test_config_resolver_openrouter_admin_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_ADMIN_KEY", "env-or-admin-key")

    config_path = tmp_path / "nonexistent.json"
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    assert "openrouter" in config.enabled_providers
    assert config.providers["openrouter"].api_key == "env-or-admin-key"

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

def test_config_resolver_enabled_env_and_json(tmp_path, monkeypatch):
    # Test JSON configuration of enabled
    config_path = tmp_path / "config.json"
    data = {
        "providers": {
            "kimi": { "apiKey": "kimi-key", "enabled": True },
            "openai": { "apiKey": "openai-key", "enabled": False }
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    # Test env override of enabled
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_ENABLED", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    # Check that only kimi and anthropic are enabled
    assert "kimi" in config.enabled_providers
    assert "anthropic" in config.enabled_providers
    assert "openai" not in config.enabled_providers
    assert "openrouter" not in config.enabled_providers

    assert config.providers["kimi"].enabled is True
    assert config.providers["openai"].enabled is False
    assert config.providers["openrouter"].enabled is False
    assert config.providers["anthropic"].enabled is True

def test_config_resolver_ordering(tmp_path):
    # Test custom providers list order in JSON
    config_path = tmp_path / "config.json"
    data = {
        "providers": {
            "openrouter": {},
            "kimi": {}
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    # Expected order: JSON defined order (openrouter, kimi), then default remaining order (anthropic, openai)
    assert config.provider_order == ["openrouter", "kimi", "anthropic", "openai"]

def test_config_resolver_theme(tmp_path, monkeypatch):
    # 1. JSON config theme
    config_path = tmp_path / "config.json"
    data = {
        "general": {
            "theme": "cyberpunk-dark"
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert config.theme == "cyberpunk-dark"

    # 2. Env variable theme override (when JSON has no theme)
    config_path_empty = tmp_path / "config_empty.json"
    with open(config_path_empty, "w", encoding="utf-8") as f:
        json.dump({}, f)

    monkeypatch.setenv("KIMI_USAGE_THEME", "nordic-dark")
    resolver2 = ConfigResolver(config_path=str(config_path_empty))
    config2 = resolver2.resolve()
    assert config2.theme == "nordic-dark"


def test_config_resolver_language_and_visible_providers(tmp_path):
    config_path = tmp_path / "config.json"
    data = {
        "general": {
            "theme": "matisse-dark",
            "language": "zh",
            "visibleProviders": ["openai", "kimi"]
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert config.theme == "matisse-dark"
    assert config.language == "zh"
    assert config.visible_providers == ["openai", "kimi"]


def test_config_resolver_unknown_provider(tmp_path):
    config_path = tmp_path / "config.json"
    data = {
        "providers": {
            "unknown-prov": { "apiKey": "some-key" },
            "kimi": { "apiKey": "kimi-key" }
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert "unknown-prov" not in config.provider_order
    assert "kimi" in config.provider_order


def test_config_resolver_or_metric(tmp_path, monkeypatch):
    # Default
    config_path = tmp_path / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({}, f)
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert config.or_metric == "requests"

    # JSON config
    data = {"general": {"orMetric": "tokens"}}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    resolver2 = ConfigResolver(config_path=str(config_path))
    config2 = resolver2.resolve()
    assert config2.or_metric == "tokens"

    # Invalid value falls back to requests
    data = {"general": {"orMetric": "invalid"}}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    resolver3 = ConfigResolver(config_path=str(config_path))
    config3 = resolver3.resolve()
    assert config3.or_metric == "requests"


def test_config_resolver_openrouter_management_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "env-or-mgmt-key")

    config_path = tmp_path / "nonexistent.json"
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    assert config.providers["openrouter"].management_key == "env-or-mgmt-key"


def test_save_theme_or_metric(tmp_path):
    from kimi_code_usage.config import save_theme
    dest = tmp_path / "config.json"
    save_theme("blue-dark", or_metric="tokens", days_window=60, config_path=dest)
    data = json.loads(dest.read_text())
    assert data["general"]["orMetric"] == "tokens"
    assert data["general"]["daysWindow"] == 60


def test_config_resolver_days_window(tmp_path):
    config_path = tmp_path / "config.json"

    # default
    resolver = ConfigResolver(config_path=str(config_path))
    assert resolver.resolve().days_window == 30

    # valid JSON value
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {"daysWindow": 7}}, f)
    assert ConfigResolver(config_path=str(config_path)).resolve().days_window == 7

    # invalid type falls back to 30
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {"daysWindow": "abc"}}, f)
    assert ConfigResolver(config_path=str(config_path)).resolve().days_window == 30

    # out-of-range value falls back to 30
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {"daysWindow": 100}}, f)
    assert ConfigResolver(config_path=str(config_path)).resolve().days_window == 30


