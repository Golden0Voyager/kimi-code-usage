"""
Anthropic quota provider (API key, opt-in).

Anthropic exposes no public usage endpoint for ordinary ``sk-ant-`` keys. The
only endpoint that reports the subscription windows is ``/api/oauth/usage``,
which expects a Claude Code OAuth token — so this provider takes whatever key
the user supplied and says plainly when that key cannot read usage. For
subscription quotas use the ``claude`` provider instead, which reads the local
Claude Code login.

Disabled by default: enable it in the TUI settings page (``s``) or with
``ANTHROPIC_ENABLED=true`` / ``anthropic.enabled: true`` in
``~/.kimi-usage/config.json``.
"""

from __future__ import annotations

import aiohttp

from . import ProviderUsage

_UNREADABLE_KEY_HINT = (
    "This key cannot read Anthropic usage: /api/oauth/usage only accepts a "
    "Claude Code OAuth token. Use the claude provider for subscription quotas."
)


async def fetch_anthropic_usage(
    api_key: str, base_url: str, management_key: str | None = None
) -> list[ProviderUsage]:
    """Fetch Anthropic subscription usage with the configured API key.

    Parameters
    ----------
    api_key : str
        The key the user pasted (or ``ANTHROPIC_API_KEY``). Used verbatim as a
        bearer token.
    base_url : str
        Base URL for the Anthropic API (default: ``https://api.anthropic.com``).
    management_key : str | None
        Ignored.
    """
    url = f"{base_url.rstrip('/')}/api/oauth/usage"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with aiohttp.ClientSession() as session, session.get(url, headers=headers) as resp:
        if resp.status in (401, 403):
            return [
                ProviderUsage(
                    provider="anthropic",
                    label="API Plan",
                    used=0.0,
                    limit=None,
                    remaining=None,
                    percent=None,
                    reset_at=None,
                    unit="text",
                    text_value=_UNREADABLE_KEY_HINT,
                )
            ]
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Anthropic API Error {resp.status}: {text[:500]}")
        data = await resp.json()

    five_hour = data.get("five_hour") or {}
    seven_day = data.get("seven_day") or {}
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
            unit="%",
        ),
        ProviderUsage(
            provider="anthropic",
            label="7 Days",
            used=seven_day_pct,
            limit=100.0,
            remaining=100.0 - seven_day_pct,
            percent=seven_day_pct,
            reset_at=None,
            unit="%",
        ),
    ]
