import asyncio
from dataclasses import dataclass, field

from kimi_code_usage.config import AppConfig


@dataclass
class ModelUsage:
    model: str
    spend: float = 0.0
    requests: float = 0.0
    prompt_tokens: float = 0.0
    completion_tokens: float = 0.0
    reasoning_tokens: float = 0.0


@dataclass
class DailyUsage:
    date: str
    models: list[ModelUsage] = field(default_factory=list)
    total: float = 0.0


@dataclass
class ActivityTotals:
    spend: float = 0.0
    requests: float = 0.0
    prompt_tokens: float = 0.0
    completion_tokens: float = 0.0
    reasoning_tokens: float = 0.0


@dataclass
class ProviderUsage:
    provider: str              # "kimi" | "openai" | "anthropic" | "openrouter"
    label: str                 # e.g., "Weekly Usage", "5 Hours", "Cost"
    used: float
    limit: float | None     # None if unlimited
    remaining: float | None
    percent: float | None   # 0-100, None if no limit
    reset_at: str | None    # ISO timestamp or formatted reset date
    unit: str                  # "%" | "tokens" | "$" | "credits"
    countdown: str | None = None # Reset countdown, e.g. "5d 12h"
    text_value: str | None = None
    activity_totals: ActivityTotals | None = None
    top_models: list[ModelUsage] | None = None
    daily_activity: list[DailyUsage] | None = None

# We will dynamically import fetchers to avoid circular dependencies
# and make it easier to load/mock them.

async def dispatch_all(config: AppConfig) -> tuple[dict[str, list[ProviderUsage]], dict[str, str]]:
    """
    Fetch usage from all enabled providers in parallel.
    Returns a tuple of (results, errors) dicts.
    """
    from .anthropic import fetch_anthropic_usage
    from .claude import fetch_claude_usage
    from .codex import fetch_codex_usage
    from .kimi import fetch_kimi_usage
    from .openai import fetch_openai_usage
    from .openrouter import fetch_openrouter_usage

    fetchers = {
        "kimi": fetch_kimi_usage,
        "openai": fetch_openai_usage,
        "anthropic": fetch_anthropic_usage,
        "openrouter": fetch_openrouter_usage,
        "codex": fetch_codex_usage,
        "claude": fetch_claude_usage,
    }

    results: dict[str, list[ProviderUsage]] = {}
    errors: dict[str, str] = {}

    enabled = config.enabled_providers
    if not enabled:
        return results, errors

    async def fetch_one(provider_name: str) -> tuple[str, list[ProviderUsage] | None, str | None]:
        fetch_func = fetchers.get(provider_name)
        if not fetch_func:
            return provider_name, None, f"Unknown provider {provider_name}"

        p_conf = config.providers.get(provider_name)
        if not p_conf or not p_conf.api_key or not p_conf.base_url:
            return provider_name, None, "Not configured"

        try:
            # 10s timeout
            res = await asyncio.wait_for(
                fetch_func(p_conf.api_key, p_conf.base_url, management_key=p_conf.management_key),
                timeout=10.0
            )
            return provider_name, res, None
        except TimeoutError:
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
