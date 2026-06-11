import aiohttp
from datetime import datetime, timedelta
from typing import List
from . import ProviderUsage

async def fetch_openai_usage(api_key: str, base_url: str) -> List[ProviderUsage]:
    headers = {"Authorization": f"Bearer {api_key}"}

    # Calculate start_time (1st day of current month) and end_time (tomorrow)
    now = datetime.now()
    start_str = now.strftime("%Y-%m-01")
    end_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    base_url_stripped = base_url.rstrip('/')
    if base_url_stripped.endswith('/v1'):
        completions_url = f"{base_url_stripped}/organization/usage/completions?start_time={start_str}&end_time={end_str}"
        costs_url = f"{base_url_stripped}/organization/usage/costs?start_time={start_str}&end_time={end_str}"
    else:
        completions_url = f"{base_url_stripped}/v1/organization/usage/completions?start_time={start_str}&end_time={end_str}"
        costs_url = f"{base_url_stripped}/v1/organization/usage/costs?start_time={start_str}&end_time={end_str}"

    async with aiohttp.ClientSession() as session:
        async with session.get(completions_url, headers=headers) as resp:
            if resp.status in (401, 403):
                raise Exception("Requires Org Admin Key")
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"OpenAI API Error {resp.status}: {text}")
            completions_data = await resp.json()

        cost_value = 0.0
        try:
            async with session.get(costs_url, headers=headers) as resp_cost:
                if resp_cost.status == 200:
                    costs_data = await resp_cost.json()
                    for item in costs_data.get("data", []):
                        amt = item.get("amount", {})
                        if isinstance(amt, dict):
                            val = amt.get("value")
                            if val is not None:
                                cost_value += float(val)
        except Exception:
            pass  # Ignore cost fetch errors as optional fallback

    total_input = 0
    total_output = 0
    for bucket in completions_data.get("data", []):
        total_input += bucket.get("input_tokens", 0)
        total_output += bucket.get("output_tokens", 0)

    total_tokens = total_input + total_output

    return [
        ProviderUsage(
            provider="openai",
            label="Tokens",
            used=float(total_tokens),
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="tokens"
        ),
        ProviderUsage(
            provider="openai",
            label="Cost",
            used=cost_value,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="$"
        )
    ]
