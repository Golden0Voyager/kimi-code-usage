import json
from unittest.mock import patch

import pytest

from kimi_code_usage.config import AppConfig, ConfigResolver


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Completely clear all related environment variables to ensure test isolation
    for key in [
        "KIMI_API_KEY",
        "KIMI_CODING_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_ADMIN_KEY",
        "OPENROUTER_MANAGEMENT_KEY",
        "KIMI_BASE_URL",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "OPENROUTER_BASE_URL",
        "KIMI_MONTHLY_USAGE",
    ]:
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
            "kimi": {"apiKey": "kimi-key", "baseUrl": "https://custom.kimi"},
            "openai": {"apiKey": "openai-key"},
        },
        "general": {"refreshIntervalMinutes": 10, "outputMode": "plain"},
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    assert config.refresh_interval_minutes == 10
    assert config.output_mode == "plain"
    assert "kimi" in config.enabled_providers
    # openai 是 API 直连类：有 key 也不再自动开，须显式 enabled 或 OPENAI_ENABLED=1
    assert "openai" not in config.enabled_providers
    assert "anthropic" not in config.enabled_providers

    assert config.providers["kimi"].api_key == "kimi-key"
    assert config.providers["kimi"].base_url == "https://custom.kimi"
    assert config.providers["openai"].api_key == "openai-key"
    assert config.providers["openai"].base_url == "https://api.openai.com"


def test_config_resolver_openai_explicit_enabled(tmp_path):
    config_path = tmp_path / "valid.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"providers": {"openai": {"apiKey": "sk-x", "enabled": True}}}, f)

    config = ConfigResolver(config_path=str(config_path)).resolve()

    assert "openai" in config.enabled_providers
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"providers": {"openai": {"apiKey": "sk-x"}}}, f)
    assert "openai" not in ConfigResolver(config_path=str(config_path)).resolve().enabled_providers


def test_config_resolver_env_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "env-kimi-key")
    monkeypatch.setenv("KIMI_BASE_URL", "https://env.kimi")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic-key")

    config_path = tmp_path / "nonexistent.json"
    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    assert "kimi" in config.enabled_providers
    # anthropic 现在跟 codex/claude 同一档：默认关，须 ANTHROPIC_ENABLED=1 显式开启
    assert "anthropic" not in config.enabled_providers
    assert "openai" not in config.enabled_providers
    assert "openrouter" not in config.enabled_providers

    assert config.providers["kimi"].api_key == "env-kimi-key"
    assert config.providers["kimi"].base_url == "https://env.kimi"
    assert config.providers["anthropic"].api_key == "env-anthropic-key"
    assert config.providers["anthropic"].base_url == "https://api.anthropic.com"


def test_config_resolver_anthropic_opt_in_via_env_and_json(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.delenv("ANTHROPIC_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # 默认关：没 key 也没 enabled
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({}, f)
    assert "anthropic" not in ConfigResolver(config_path=str(config_path)).resolve().enabled_providers

    # API 直连类：只有 enabled 还不够，仍然要有 key
    monkeypatch.setenv("ANTHROPIC_ENABLED", "1")
    assert "anthropic" not in ConfigResolver(config_path=str(config_path)).resolve().enabled_providers

    # 设置页粘贴 key 后会写成 apiKey + enabled
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"providers": {"anthropic": {"apiKey": "sk-ant-pasted", "enabled": True}}}, f)
    resolved = ConfigResolver(config_path=str(config_path)).resolve()
    assert resolved.providers["anthropic"].api_key == "sk-ant-pasted"
    assert "anthropic" in resolved.enabled_providers


def test_config_resolver_subscription_provider_autodetect(tmp_path, monkeypatch):
    """codex/claude 检测到本机登录文件就默认开，不需要任何配置。"""
    from kimi_code_usage import config as cfg_mod

    config_path = tmp_path / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({}, f)
    for key in ("CODEX_ENABLED", "CLAUDE_ENABLED"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(cfg_mod, "local_login_present", lambda p: p == "codex")
    resolved = ConfigResolver(config_path=str(config_path)).resolve()
    assert "codex" in resolved.enabled_providers
    assert "claude" not in resolved.enabled_providers

    # 没登录文件 → 默认关
    monkeypatch.setattr(cfg_mod, "local_login_present", lambda p: False)
    resolved = ConfigResolver(config_path=str(config_path)).resolve()
    assert "codex" not in resolved.enabled_providers

    # 用户手动关掉要能覆盖自动检测
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"providers": {"codex": {"enabled": False}}}, f)
    monkeypatch.setattr(cfg_mod, "local_login_present", lambda p: True)
    assert "codex" not in ConfigResolver(config_path=str(config_path)).resolve().enabled_providers


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
    data = {"providers": {"kimi": {"apiKey": "kimi-json-key"}}}
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
            "kimi": {"apiKey": "kimi-key", "enabled": True},
            "openai": {"apiKey": "openai-key", "enabled": False},
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
    data = {"providers": {"openrouter": {}, "kimi": {}}}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()

    # Expected order: JSON defined order (openrouter, kimi), then default remaining order (anthropic, openai, codex, claude)
    assert config.provider_order == ["openrouter", "kimi", "anthropic", "openai", "codex", "claude"]


def test_config_resolver_theme(tmp_path, monkeypatch):
    # 1. JSON config theme
    config_path = tmp_path / "config.json"
    data = {"general": {"theme": "cyberpunk-dark"}}
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
    data = {"general": {"theme": "matisse-dark", "language": "zh", "visibleProviders": ["openai", "kimi"]}}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert config.theme == "matisse-dark"
    assert config.language == "zh"
    assert config.visible_providers == ["openai", "kimi"]


def test_config_resolver_provider_order(tmp_path):
    config_path = tmp_path / "config.json"
    data = {"general": {"providerOrder": ["claude", "kimi", "openai", "anthropic", "openrouter", "codex"]}}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver = ConfigResolver(config_path=str(config_path))
    config = resolver.resolve()
    assert config.provider_order == ["claude", "kimi", "openai", "anthropic", "openrouter", "codex"]

    # Unknown providers are ignored, missing providers are appended from defaults
    data = {"general": {"providerOrder": ["kimi", "unknown-prov", "openai"]}}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    resolver2 = ConfigResolver(config_path=str(config_path))
    config2 = resolver2.resolve()
    assert config2.provider_order == ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]


def test_config_resolver_unknown_provider(tmp_path):
    config_path = tmp_path / "config.json"
    data = {"providers": {"unknown-prov": {"apiKey": "some-key"}, "kimi": {"apiKey": "kimi-key"}}}
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


def test_save_theme_provider_order(tmp_path):
    from kimi_code_usage.config import save_theme

    dest = tmp_path / "config.json"
    save_theme(
        "blue-dark",
        provider_order=["kimi", "openai", "anthropic", "openrouter", "codex", "claude"],
        config_path=dest,
    )
    data = json.loads(dest.read_text())
    assert data["general"]["providerOrder"] == [
        "kimi",
        "openai",
        "anthropic",
        "openrouter",
        "codex",
        "claude",
    ]


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


def test_config_resolver_kimi_monthly_defaults_off(tmp_path):
    config_path = tmp_path / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {"refreshIntervalMinutes": 5}}, f)

    assert ConfigResolver(config_path=str(config_path)).resolve().kimi_monthly is False


def test_config_resolver_kimi_monthly_from_json_and_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.delenv("KIMI_MONTHLY_USAGE", raising=False)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {"kimiMonthly": True}}, f)
    assert ConfigResolver(config_path=str(config_path)).resolve().kimi_monthly is True

    # 显式 false 不被 env 覆盖
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {"kimiMonthly": False}}, f)
    monkeypatch.setenv("KIMI_MONTHLY_USAGE", "1")
    assert ConfigResolver(config_path=str(config_path)).resolve().kimi_monthly is False

    # 未写 kimiMonthly 时才回落到 env
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"general": {}}, f)
    assert ConfigResolver(config_path=str(config_path)).resolve().kimi_monthly is True


def test_save_theme_accepts_str_config_path(tmp_path):
    from kimi_code_usage.config import save_theme

    path = tmp_path / "custom.json"
    save_theme("mint-dark", config_path=str(path))

    assert json.loads(path.read_text(encoding="utf-8"))["general"]["theme"] == "mint-dark"
