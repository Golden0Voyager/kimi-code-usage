import aiohttp
from typing import List
from . import ProviderUsage

async def fetch_anthropic_usage(api_key: str, base_url: str) -> List[ProviderUsage]:
    if api_key.startswith("sk-ant-"):
        return [
            ProviderUsage(
                provider="anthropic",
                label="API Plan",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text"
            )
        ]

    url = f"{base_url.rstrip('/')}/api/oauth/usage"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status in (401, 403):
                return [
                    ProviderUsage(
                        provider="anthropic",
                        label="API Plan (No usage API)",
                        used=0.0,
                        limit=None,
                        remaining=None,
                        percent=None,
                        reset_at=None,
                        unit="text"
                    )
                ]
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Anthropic API Error {resp.status}: {text}")
            data = await resp.json()

    five_hour = data.get("five_hour", {})
    seven_day = data.get("seven_day", {})
    five_hour_pct = float(five_hour.get("utilization", 0.0)) * 100.0 if isinstance(five_hour, dict) else 0.0
    seven_day_pct = float(seven_day.get("utilization", 0.0)) * 100.0 if isinstance(seven_day, dict) else 0.0

    return [
        ProviderUsage(
            provider="anthropic",
            label="5 Hours",
            used=five_hour_pct,
            limit=100.0,
            remaining=100.0 - five_hour_pct,
            percent=five_hour_pct,
            reset_at=None,
            unit="%"
        ),
        ProviderUsage(
            provider="anthropic",
            label="7 Days",
            used=seven_day_pct,
            limit=100.0,
            remaining=100.0 - seven_day_pct,
            percent=seven_day_pct,
            reset_at=None,
            unit="%"
        )
    ]
