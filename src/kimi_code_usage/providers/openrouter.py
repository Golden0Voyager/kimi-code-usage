import aiohttp
from typing import List
from . import ProviderUsage

async def fetch_openrouter_usage(api_key: str, base_url: str) -> List[ProviderUsage]:
    url = f"{base_url.rstrip('/')}/v1/auth/key"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"OpenRouter API Error {resp.status}: {text}")
            payload = await resp.json()

    data = payload.get("data", {})
    usage = data.get("usage")
    limit = data.get("limit")

    used_val = float(usage) if usage is not None else 0.0
    limit_val = float(limit) if limit is not None else None

    remaining_val = (limit_val - used_val) if limit_val is not None else None
    percent_val = (used_val / limit_val * 100) if (limit_val is not None and limit_val > 0) else None

    return [
        ProviderUsage(
            provider="openrouter",
            label="Credits",
            used=used_val,
            limit=limit_val,
            remaining=remaining_val,
            percent=percent_val,
            reset_at=None,
            unit="$"
        )
    ]
