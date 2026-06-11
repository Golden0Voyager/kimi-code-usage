import aiohttp
import asyncio
from typing import List
from . import ProviderUsage

async def fetch_openrouter_usage(api_key: str, base_url: str) -> List[ProviderUsage]:
    base_url_stripped = base_url.rstrip('/')
    
    if base_url_stripped.endswith('/v1'):
        key_url = f"{base_url_stripped}/auth/key"
        credits_url = f"{base_url_stripped}/credits"
    else:
        key_url = f"{base_url_stripped}/v1/auth/key"
        credits_url = f"{base_url_stripped}/v1/credits"

    headers = {"Authorization": f"Bearer {api_key}"}
    
    key_payload = None
    credits_payload = None

    async with aiohttp.ClientSession() as session:
        async def fetch_key():
            async with session.get(key_url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"OpenRouter API Error {resp.status}: {text}")
                return await resp.json()

        async def fetch_credits():
            async with session.get(credits_url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
            return None

        # Gather both, credits is optional so we handle exception or failure gracefully
        results = await asyncio.gather(
            fetch_key(),
            fetch_credits(),
            return_exceptions=True
        )
        key_payload, credits_payload = results[0], results[1]

    if isinstance(key_payload, Exception):
        raise key_payload

    if isinstance(credits_payload, Exception):
        credits_payload = None

    res = []
    
    key_data = key_payload.get("data", {})
    key_usage = key_data.get("usage")
    key_limit = key_data.get("limit")

    key_used_val = float(key_usage) if key_usage is not None else 0.0
    key_limit_val = float(key_limit) if key_limit is not None else None

    # Try to extract total credits/usage from credits API response
    credits_data = credits_payload.get("data", {}) if credits_payload else None
    
    if credits_data:
        total_credits = credits_data.get("total_credits")
        total_usage = credits_data.get("total_usage")
        
        if total_credits is not None and total_usage is not None:
            t_credits = float(total_credits)
            t_usage = float(total_usage)
            remaining_val = t_credits - t_usage
            percent_val = (t_usage / t_credits * 100) if t_credits > 0 else None
            
            # 1. Total Credits for the account
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
            
            # 2. Key-specific Usage
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
        # Fallback to key usage as "Credits" if credits API failed or wasn't available
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

    # 3. Key Label (Name)
    key_label = key_data.get("label")
    if key_label:
        is_mgmt = key_label.startswith("sk-") and "..." in key_label
        if is_mgmt:
            display_label = "Management Key"
            display_value = key_label.replace("...", "*********")
        else:
            display_label = "Key Name"
            display_value = key_label

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

    # 3.1. Free Tier
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

    # 3.2. Limit Reset
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

    # 3.3. Expires At
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

    # 3.4. Is Provisioning
    is_provisioning = key_data.get("is_provisioning_key")
    if is_provisioning is not None:
        res.append(ProviderUsage(
            provider="openrouter",
            label="Is Provisioning",
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value="Yes" if is_provisioning else "No"
        ))

    # 4. Rate Limit
    rate_limit = key_data.get("rate_limit", {})
    if isinstance(rate_limit, dict):
        reqs = rate_limit.get("requests")
        interval = rate_limit.get("interval")
        if reqs is not None and interval is not None and reqs > 0:
            res.append(ProviderUsage(
                provider="openrouter",
                label="Rate Limit",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value=f"{reqs} req/{interval}"
            ))

    # 5. Period Usage (Daily, Weekly, Monthly)
    u_daily = float(key_data.get("usage_daily") if key_data.get("usage_daily") is not None else 0.0)
    u_weekly = float(key_data.get("usage_weekly") if key_data.get("usage_weekly") is not None else 0.0)
    u_monthly = float(key_data.get("usage_monthly") if key_data.get("usage_monthly") is not None else 0.0)

    import os
    lang = os.getenv("LANG", "en")
    is_zh = "zh" in lang.lower()
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

    return res

