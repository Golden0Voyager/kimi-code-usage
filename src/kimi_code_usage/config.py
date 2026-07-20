import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".kimi-usage" / "config.json"


@dataclass
class ProviderConfig:
    api_key: str | None = None
    base_url: str | None = None
    enabled: bool = True
    management_key: str | None = None


@dataclass
class AppConfig:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    refresh_interval_minutes: int = 5
    output_mode: str = "rich"
    provider_order: list[str] = field(default_factory=list)
    theme: str = "blue-dark"
    language: str | None = None
    visible_providers: list[str] | None = None
    or_metric: str = "requests"
    days_window: int = 30

    @property
    def enabled_providers(self) -> list[str]:
        return [name for name, p_conf in self.providers.items() if p_conf.api_key and p_conf.enabled]


class ConfigResolver:
    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config = AppConfig()

    def resolve(self) -> AppConfig:
        # 1. Load from JSON if exists
        json_data = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    json_data = json.load(f)
            except Exception:
                pass  # Ignore invalid JSON, fall back to default/env

        # Parse JSON config
        providers_data = json_data.get("providers", {})
        general_data = json_data.get("general", {})

        self.config.refresh_interval_minutes = general_data.get("refreshIntervalMinutes", 5)
        self.config.output_mode = general_data.get("outputMode", "rich")

        # Get theme from JSON, else ENV, default blue-dark
        theme = general_data.get("theme")
        if not theme:
            theme = os.getenv("KIMI_USAGE_THEME", "blue-dark")
        self.config.theme = theme

        # Get language, visible providers, and provider order from JSON
        self.config.language = general_data.get("language")
        self.config.visible_providers = general_data.get("visibleProviders")
        saved_provider_order = general_data.get("providerOrder")

        # Get OpenRouter metric preference, default requests
        or_metric = general_data.get("orMetric", "requests")
        if or_metric not in ("spend", "requests", "tokens"):
            or_metric = "requests"
        self.config.or_metric = or_metric

        # Get days window for daily chart, default 30
        days_window = general_data.get("daysWindow", 30)
        try:
            days_window = int(days_window)
        except (TypeError, ValueError):
            days_window = 30
        if days_window not in (7, 14, 30, 60, 90):
            days_window = 30
        self.config.days_window = days_window

        # 2. Setup providers
        all_providers = ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]

        # Envs map
        env_keys = {
            "kimi": ("KIMI_API_KEY", "KIMI_CODING_API_KEY"),
            "openai": ("OPENAI_API_KEY",),
            "anthropic": ("ANTHROPIC_API_KEY",),
            "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_ADMIN_KEY"),
            "codex": ("CODEX_API_KEY",),
            "claude": ("CLAUDE_API_KEY",),
        }

        env_urls = {
            "kimi": "KIMI_BASE_URL",
            "openai": "OPENAI_BASE_URL",
            "anthropic": "ANTHROPIC_BASE_URL",
            "openrouter": "OPENROUTER_BASE_URL",
            "codex": "CODEX_BASE_URL",
            "claude": "CLAUDE_BASE_URL",
        }

        default_urls = {
            "kimi": "https://api.kimi.com/coding/v1",
            "openai": "https://api.openai.com",
            "anthropic": "https://api.anthropic.com",
            "openrouter": "https://openrouter.ai/api",
            "codex": "https://chatgpt.com/backend-api",
            "claude": "https://api.anthropic.com",
        }

        for p in all_providers:
            p_data = providers_data.get(p, {})
            # Get API Key from JSON, else ENV
            api_key = p_data.get("apiKey")
            if not api_key:
                for env_var in env_keys[p]:
                    val = os.getenv(env_var)
                    if val:
                        api_key = val
                        break

            # Get Base URL from JSON, else ENV, else Default
            base_url = p_data.get("baseUrl")
            if not base_url:
                base_url = os.getenv(env_urls[p])
            if not base_url:
                base_url = default_urls[p]

            # Get optional management key for OpenRouter (activity endpoint)
            management_key = None
            if p == "openrouter":
                management_key = (
                    p_data.get("managementApiKey")
                    or os.getenv("OPENROUTER_MANAGEMENT_KEY")
                    or os.getenv("OPENROUTER_ADMIN_KEY")
                )

            # Codex & Claude: default-off, read local auth files directly
            if p in ("codex", "claude"):
                enabled = p_data.get("enabled")
                if enabled is None:
                    env_enabled = os.getenv(f"{p.upper()}_ENABLED", "").lower()
                    enabled = env_enabled in ("true", "1", "yes")
                if enabled:
                    api_key = "enabled"  # Sentinel: passes enabled_providers check
            else:
                # Get Enabled status from JSON, else ENV, default True
                enabled = p_data.get("enabled")
                if enabled is None:
                    env_enabled = os.getenv(f"{p.upper()}_ENABLED")
                    if env_enabled is not None:
                        enabled = env_enabled.lower() not in ("false", "0", "no")
                    else:
                        enabled = True

            self.config.providers[p] = ProviderConfig(
                api_key=api_key if api_key else None,
                base_url=base_url,
                enabled=enabled,
                management_key=management_key if management_key else None,
            )

        # 3. Determine provider ordering
        default_order = ["anthropic", "openai", "openrouter", "kimi", "codex", "claude"]
        json_providers = list(providers_data.keys())

        final_order = []
        for p in json_providers:
            if p in all_providers and p not in final_order:
                final_order.append(p)
        for p in default_order:
            if p not in final_order:
                final_order.append(p)

        # Persisted order from settings view takes precedence over derived order
        if saved_provider_order:
            saved_order = [p for p in saved_provider_order if p in all_providers]
            for p in default_order:
                if p not in saved_order:
                    saved_order.append(p)
            final_order = saved_order

        self.config.provider_order = final_order

        return self.config


def save_theme(
    theme_name: str,
    language: str | None = None,
    visible_providers: list[str] | None = None,
    or_metric: str | None = None,
    days_window: int | None = None,
    provider_order: list[str] | None = None,
    config_path: Path | None = None,
) -> None:
    """Persist settings into ``general`` in the JSON config file.

    All other settings in the file are preserved.  The config directory is
    created automatically if it does not exist yet.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}

    general = data.get("general", {})
    general["theme"] = theme_name
    if language is not None:
        general["language"] = language
    if visible_providers is not None:
        general["visibleProviders"] = visible_providers
    if or_metric is not None:
        general["orMetric"] = or_metric
    if days_window is not None:
        general["daysWindow"] = days_window
    if provider_order is not None:
        general["providerOrder"] = provider_order
    data["general"] = general

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
