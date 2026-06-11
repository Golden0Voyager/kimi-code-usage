import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from kimi_code_usage.config import AppConfig

@dataclass
class ProviderUsage:
    provider: str              # "kimi" | "openai" | "anthropic" | "openrouter"
    label: str                 # e.g., "Weekly Usage", "5 Hours", "Cost"
    used: float
    limit: Optional[float]     # None if unlimited
    remaining: Optional[float]
    percent: Optional[float]   # 0-100, None if no limit
    reset_at: Optional[str]    # ISO timestamp or formatted reset date
    unit: str                  # "%" | "tokens" | "$" | "credits"
    countdown: Optional[str] = None # Reset countdown, e.g. "5d 12h"
    text_value: Optional[str] = None

# We will dynamically import fetchers to avoid circular dependencies
# and make it easier to load/mock them.

async def dispatch_all(config: AppConfig) -> Tuple[Dict[str, List[ProviderUsage]], Dict[str, str]]:
    """
    Fetch usage from all enabled providers in parallel.
    Returns a tuple of (results, errors) dicts.
    """
    from .kimi import fetch_kimi_usage
    from .openai import fetch_openai_usage
    from .anthropic import fetch_anthropic_usage
    from .openrouter import fetch_openrouter_usage

    fetchers = {
        "kimi": fetch_kimi_usage,
        "openai": fetch_openai_usage,
        "anthropic": fetch_anthropic_usage,
        "openrouter": fetch_openrouter_usage,
    }

    results: Dict[str, List[ProviderUsage]] = {}
    errors: Dict[str, str] = {}

    enabled = config.enabled_providers
    if not enabled:
        return results, errors

    async def fetch_one(provider_name: str) -> Tuple[str, Optional[List[ProviderUsage]], Optional[str]]:
        fetch_func = fetchers.get(provider_name)
        if not fetch_func:
            return provider_name, None, f"Unknown provider {provider_name}"

        p_conf = config.providers.get(provider_name)
        if not p_conf or not p_conf.api_key or not p_conf.base_url:
            return provider_name, None, "Not configured"

        try:
            # 10s timeout
            res = await asyncio.wait_for(fetch_func(p_conf.api_key, p_conf.base_url), timeout=10.0)
            return provider_name, res, None
        except asyncio.TimeoutError:
            return provider_name, None, "Request timed out"
        except Exception as e:
            return provider_name, None, str(e)

    tasks = [fetch_one(p) for p in enabled]
    responses = await asyncio.gather(*tasks)

    for provider, res, err in responses:
        if err:
            errors[provider] = err
        elif res is not None:
            results[provider] = res

    return results, errors
