"""
Anthropic subscription quota provider.

Reads the Claude Code OAuth token — from the macOS login keychain, or from
``~/.claude/.credentials.json`` — and calls the Anthropic OAuth usage endpoint
to retrieve subscription usage limits.

The provider is **disabled by default** — enable it with
``ANTHROPIC_ENABLED=true`` or ``anthropic.enabled: true`` in
``~/.kimi-usage/config.json``.
"""

from __future__ import annotations

from collections.abc import Mapping

import aiohttp

from . import ProviderUsage
from .claude import (
    CLAUDE_BETA_HEADER,
    _parse_usage_response,
    _read_oauth_token,
)


async def fetch_anthropic_usage(
    api_key: str, base_url: str, management_key: str | None = None
) -> list[ProviderUsage]:
    """Fetch Anthropic/Claude subscription usage from the OAuth usage endpoint.

    Parameters
    ----------
    api_key : str
        **Ignored** — this provider reads credentials from the local Claude
        Code login (keychain or ``~/.claude/.credentials.json``) directly,
        just like ``claude``. Users who do not use Claude Code will see a
        clear error instead of a useless "API Plan" row.
    base_url : str
        Base URL for the Anthropic API (default: ``https://api.anthropic.com``).
    management_key : str | None
        Ignored.
    """
    oauth_token = _read_oauth_token()

    usage_url = f"{base_url.rstrip('/')}/api/oauth/usage"
    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "anthropic-beta": CLAUDE_BETA_HEADER,
    }

    async with aiohttp.ClientSession() as session, session.get(usage_url, headers=headers) as resp:
        if resp.status in (401, 403):
            raise RuntimeError(
                "Anthropic/Claude API returned 401/403. The OAuth token may be "
                "expired — try re-running `claude login`."
            )
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Anthropic API Error {resp.status}: {text[:500]}")
        data: Mapping = await resp.json()

    return _parse_usage_response(data)
