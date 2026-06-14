import aiohttp
import asyncio
import os
from typing import List, Optional
from . import (
    ProviderUsage,
    ActivityTotals,
    DailyUsage,
    ModelUsage,
)


def _base_url_v1(base_url: str) -> str:
    base = base_url.rstrip('/')
    if base.endswith('/v1'):
        return base
    return base + '/v1'


def _get_lang() -> bool:
    return "zh" in os.getenv("LANG", "en").lower()


def _build_activity(items: List[dict]) -> tuple[ActivityTotals, List[ModelUsage]]:
    totals = ActivityTotals()
    by_model: dict[str, ModelUsage] = {}

    for item in items:
        totals.spend += float(item.get("usage") or 0)
        totals.requests += float(item.get("requests") or 0)
        totals.prompt_tokens += float(item.get("prompt_tokens") or 0)
        totals.completion_tokens += float(item.get("completion_tokens") or 0)
        totals.reasoning_tokens += float(item.get("reasoning_tokens") or 0)

        model_name = item.get("model", "unknown")
        if model_name not in by_model:
            by_model[model_name] = ModelUsage(model=model_name)
        m = by_model[model_name]
        m.spend += float(item.get("usage") or 0)
        m.requests += float(item.get("requests") or 0)
        m.prompt_tokens += float(item.get("prompt_tokens") or 0)
        m.completion_tokens += float(item.get("completion_tokens") or 0)
        m.reasoning_tokens += float(item.get("reasoning_tokens") or 0)

    models = sorted(
        by_model.values(),
        key=lambda m: (m.spend, m.requests),
        reverse=True,
    )
    return totals, models


def _build_daily_activity(items: List[dict]) -> List[DailyUsage]:
    by_date: dict[str, dict[str, ModelUsage]] = {}

    for item in items:
        date = item.get("date", "")
        if not date:
            continue
        models = by_date.setdefault(date, {})
        model_name = item.get("model", "unknown")
        if model_name not in models:
            models[model_name] = ModelUsage(model=model_name)
        m = models[model_name]
        m.spend += float(item.get("usage") or 0)
        m.requests += float(item.get("requests") or 0)
        m.prompt_tokens += float(item.get("prompt_tokens") or 0)
        m.completion_tokens += float(item.get("completion_tokens") or 0)
        m.reasoning_tokens += float(item.get("reasoning_tokens") or 0)

    daily = []
    for date in sorted(by_date.keys()):
        models = sorted(
            by_date[date].values(),
            key=lambda m: m.spend,
            reverse=True,
        )
        total = sum(m.spend for m in models)
        daily.append(DailyUsage(date=date, models=models, total=total))
    return daily


def _model_short_name(model: str) -> str:
    if "/" in model:
        return model.rsplit("/", 1)[-1]
    return model


async def fetch_openrouter_usage(api_key: str, base_url: str, management_key: Optional[str] = None) -> List[ProviderUsage]:
    base = _base_url_v1(base_url)
    key_url = f"{base}/auth/key"
    credits_url = f"{base}/credits"
    activity_url = f"{base}/activity"

    key_headers = {"Authorization": f"Bearer {api_key}"}
    activity_headers = {"Authorization": f"Bearer {management_key or api_key}"}

    async with aiohttp.ClientSession() as session:
        async def fetch_key():
            async with session.get(key_url, headers=key_headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"OpenRouter API Error {resp.status}: {text}")
                return await resp.json()

        async def fetch_credits():
            async with session.get(credits_url, headers=key_headers) as resp:
                if resp.status == 200:
                    return await resp.json()
            return None

        async def fetch_activity():
            try:
                async with session.get(activity_url, headers=activity_headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                pass
            return None

        key_payload = await fetch_key()
        if isinstance(key_payload, Exception):  # pragma: no cover
            raise key_payload

        # Fetch activity for all keys; only management keys typically have access,
        # so failures are silently ignored.
        results = await asyncio.gather(fetch_credits(), fetch_activity(), return_exceptions=True)

    credits_payload = results[0]
    activity_payload = results[1]

    if isinstance(credits_payload, Exception):
        credits_payload = None
    if isinstance(activity_payload, Exception):  # pragma: no cover
        activity_payload = None

    key_data = key_payload.get("data", {})
    is_management = bool(key_data.get("is_management_key"))

    res: List[ProviderUsage] = []
    is_zh = _get_lang()

    key_usage = key_data.get("usage")
    key_limit = key_data.get("limit")
    key_used_val = float(key_usage) if key_usage is not None else 0.0
    key_limit_val = float(key_limit) if key_limit is not None else None

    credits_data = credits_payload.get("data", {}) if credits_payload else None

    if credits_data:
        total_credits = credits_data.get("total_credits")
        total_usage = credits_data.get("total_usage")
        if total_credits is not None and total_usage is not None:
            t_credits = float(total_credits)
            t_usage = float(total_usage)
            remaining_val = t_credits - t_usage
            percent_val = (t_usage / t_credits * 100) if t_credits > 0 else None

            res.append(ProviderUsage(
                provider="openrouter",
                label="Credits",
                used=t_usage,
                limit=t_credits,
                remaining=remaining_val,
                percent=percent_val,
                reset_at=None,
                unit="$"
            ))

            k_remaining = (key_limit_val - key_used_val) if key_limit_val is not None else None
            k_percent = (key_used_val / key_limit_val * 100) if (key_limit_val is not None and key_limit_val > 0) else None

            res.append(ProviderUsage(
                provider="openrouter",
                label="Key Usage",
                used=key_used_val,
                limit=key_limit_val,
                remaining=k_remaining,
                percent=k_percent,
                reset_at=None,
                unit="$"
            ))

    if not res:
        remaining_val = (key_limit_val - key_used_val) if key_limit_val is not None else None
        percent_val = (key_used_val / key_limit_val * 100) if (key_limit_val is not None and key_limit_val > 0) else None

        res.append(ProviderUsage(
            provider="openrouter",
            label="Credits",
            used=key_used_val,
            limit=key_limit_val,
            remaining=remaining_val,
            percent=percent_val,
            reset_at=None,
            unit="$"
        ))

    key_label = key_data.get("label")
    if key_label:
        if is_management:
            display_label = "Management Key"
        else:
            display_label = "Key Name"
        display_value = key_label.replace("...", "*********") if "..." in key_label else key_label

        res.append(ProviderUsage(
            provider="openrouter",
            label=display_label,
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value=display_value
        ))

    is_free_tier = key_data.get("is_free_tier")
    if is_free_tier is not None:
        res.append(ProviderUsage(
            provider="openrouter",
            label="Free Tier",
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value="Yes" if is_free_tier else "No"
        ))

    limit_reset = key_data.get("limit_reset")
    if limit_reset:
        res.append(ProviderUsage(
            provider="openrouter",
            label="Limit Reset",
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value=str(limit_reset)
        ))

    expires_at = key_data.get("expires_at")
    if expires_at:
        res.append(ProviderUsage(
            provider="openrouter",
            label="Expires At",
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value=str(expires_at)
        ))

    is_provisioning = key_data.get("is_provisioning_key")
    # NOTE: Is Provisioning is intentionally not displayed by default.
    # It remains available in key_data for future configuration if needed.
    _ = is_provisioning

    rate_limit = key_data.get("rate_limit", {})
    if isinstance(rate_limit, dict):
        reqs = rate_limit.get("requests")
        interval = rate_limit.get("interval")
        if reqs is not None and interval is not None:
            if reqs == -1:
                if is_zh:
                    interval_zh = str(interval).replace("s", "秒").replace("m", "分钟").replace("h", "小时")
                    val_str = f"无限制/{interval_zh}"
                else:
                    val_str = f"Unlimited/{interval}"
            else:
                if is_zh:
                    interval_zh = str(interval).replace("s", "秒").replace("m", "分钟").replace("h", "小时")
                    val_str = f"{reqs}次/{interval_zh}"
                else:
                    val_str = f"{reqs} req/{interval}"

            res.append(ProviderUsage(
                provider="openrouter",
                label="Rate Limit",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value=val_str
            ))

    u_daily = float(key_data.get("usage_daily") if key_data.get("usage_daily") is not None else 0.0)
    u_weekly = float(key_data.get("usage_weekly") if key_data.get("usage_weekly") is not None else 0.0)
    u_monthly = float(key_data.get("usage_monthly") if key_data.get("usage_monthly") is not None else 0.0)

    label_str = "周期已用" if is_zh else "Usage"
    if is_zh:
        text_val = f"今日: ${u_daily:.4f} | 本周: ${u_weekly:.4f} | 本月: ${u_monthly:.4f}"
    else:
        text_val = f"Daily: ${u_daily:.4f} | Weekly: ${u_weekly:.4f} | Monthly: ${u_monthly:.4f}"

    res.append(ProviderUsage(
        provider="openrouter",
        label=label_str,
        used=0.0,
        limit=None,
        remaining=None,
        percent=None,
        reset_at=None,
        unit="text",
        text_value=text_val
    ))

    if activity_payload and isinstance(activity_payload, dict):
        items = activity_payload.get("data", [])
        if isinstance(items, list) and items:
            totals, top_models = _build_activity(items)
            daily_activity = _build_daily_activity(items)

            res.append(ProviderUsage(
                provider="openrouter",
                label="Activity" if not is_zh else "活动",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value=None,
                activity_totals=totals,
            ))

            if daily_activity:
                res.append(ProviderUsage(
                    provider="openrouter",
                    label="Daily Spend" if not is_zh else "每日支出",
                    used=0.0,
                    limit=None,
                    remaining=None,
                    percent=None,
                    reset_at=None,
                    unit="text",
                    text_value=None,
                    daily_activity=daily_activity,
                ))

            if top_models:
                res.append(ProviderUsage(
                    provider="openrouter",
                    label="Top Models" if not is_zh else "Top 模型",
                    used=0.0,
                    limit=None,
                    remaining=None,
                    percent=None,
                    reset_at=None,
                    unit="text",
                    text_value=None,
                    top_models=top_models,
                ))

    return res
