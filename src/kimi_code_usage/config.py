import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_CONFIG_PATH = Path.home() / ".kimi-usage" / "config.json"

@dataclass
class ProviderConfig:
    api_key: Optional[str] = None
    base_url: Optional[str] = None

@dataclass
class AppConfig:
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    refresh_interval_minutes: int = 5
    output_mode: str = "rich"

    @property
    def enabled_providers(self) -> List[str]:
        return [name for name, p_conf in self.providers.items() if p_conf.api_key]

class ConfigResolver:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config = AppConfig()

    def resolve(self) -> AppConfig:
        # 1. Load from JSON if exists
        json_data = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
            except Exception:
                pass  # Ignore invalid JSON, fall back to default/env

        # Parse JSON config
        providers_data = json_data.get("providers", {})
        general_data = json_data.get("general", {})

        self.config.refresh_interval_minutes = general_data.get("refreshIntervalMinutes", 5)
        self.config.output_mode = general_data.get("outputMode", "rich")

        # 2. Setup providers
        all_providers = ["kimi", "openai", "anthropic", "openrouter"]

        # Envs map
        env_keys = {
            "kimi": ("KIMI_API_KEY", "KIMI_CODING_API_KEY"),
            "openai": ("OPENAI_API_KEY",),
            "anthropic": ("ANTHROPIC_API_KEY",),
            "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_ADMIN_KEY"),
        }

        env_urls = {
            "kimi": "KIMI_BASE_URL",
            "openai": "OPENAI_BASE_URL",
            "anthropic": "ANTHROPIC_BASE_URL",
            "openrouter": "OPENROUTER_BASE_URL",
        }

        default_urls = {
            "kimi": "https://api.kimi.com/coding/v1",
            "openai": "https://api.openai.com",
            "anthropic": "https://api.anthropic.com",
            "openrouter": "https://openrouter.ai/api",
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

            self.config.providers[p] = ProviderConfig(
                api_key=api_key if api_key else None,
                base_url=base_url
            )

        return self.config
