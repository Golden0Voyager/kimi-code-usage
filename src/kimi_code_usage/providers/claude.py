"""
Claude (ChatGPT) subscription quota provider.

Reads OAuth tokens from the local Claude Code credentials file
(``~/.claude/.credentials.json``) and calls the Anthropic OAuth usage
endpoint to retrieve subscription usage limits.

The provider is **disabled by default** — enable it with
``CLAUDE_ENABLED=true`` or ``claude.enabled: true`` in
``~/.kimi-usage/config.json``.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cloudscraper

from . import ProviderUsage

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

CLAUDE_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
CLAUDE_OAUTH_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_BETA_HEADER = "oauth-2025-04-20"


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _read_oauth_token() -> str:
    """Read the Claude OAuth token from the local credentials file.

    Tries, in order:
    1. ``~/.claude/.credentials.json`` → ``claudeAiOauth`` key
    2. ``CLAUDE_CODE_OAUTH_TOKEN`` environment variable
    """
    if CLAUDE_CREDENTIALS_PATH.exists():
        try:
            with open(CLAUDE_CREDENTIALS_PATH, encoding="utf-8") as f:
                creds: dict[str, Any] = json.load(f)
            token: str | None = creds.get("claudeAiOauth")
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    env_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    if env_token:
        return env_token

    raise FileNotFoundError(
        f"Claude OAuth token not found at {CLAUDE_CREDENTIALS_PATH} "
        "or in CLAUDE_CODE_OAUTH_TOKEN env var. "
        "Make sure you have logged in with `claude` CLI first."
    )


def _is_lang_zh() -> bool:
    return "zh" in os.getenv("LANG", "en").lower()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_usage_response(data: Mapping[str, Any]) -> list[ProviderUsage]:
    """Parse the Anthropic OAuth usage response into ``ProviderUsage`` rows."""
    results: list[ProviderUsage] = []
    is_zh = _is_lang_zh()

    # Window definitions: (json_key, label_en, label_zh)
    windows = [
        ("five_hour", "5 Hours", "5小时限额"),
        ("seven_day", "7 Days", "7天用量"),
        ("seven_day_sonnet", "7 Days Sonnet", "7天 Sonnet 用量"),
        ("seven_day_opus", "7 Days Opus", "7天 Opus 用量"),
    ]

    for json_key, label_en, label_zh in windows:
        window = data.get(json_key)
        if isinstance(window, Mapping):
            utilization = window.get("utilization")
            if utilization is not None:
                try:
                    pct = float(utilization) * 100.0
                except (TypeError, ValueError):
                    continue

                label = label_zh if is_zh else label_en
                results.append(
                    ProviderUsage(
                        provider="claude",
                        label=label,
                        used=pct,
                        limit=100.0,
                        remaining=max(0.0, 100.0 - pct),
                        percent=pct,
                        reset_at=None,
                        unit="%",
                    )
                )

    # Fallback if no windows were parsed
    if not results:
        raw_keys = ", ".join(str(k) for k in data.keys())
        results.append(
            ProviderUsage(
                provider="claude",
                label="API Data" if not is_zh else "API 数据",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value=raw_keys,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------


async def fetch_claude_usage(
    api_key: str, base_url: str, management_key: str | None = None
) -> list[ProviderUsage]:
    """Fetch Claude subscription usage from the Anthropic OAuth usage endpoint.

    Parameters
    ----------
    api_key : str
        Ignored — the provider reads the credentials file directly.
    base_url : str
        Base URL for the Anthropic API
        (default: ``https://api.anthropic.com``).
    management_key : str | None
        Ignored.

    Raises
    ------
    FileNotFoundError
        If the credentials file is missing and no env var is set.
    RuntimeError
        If the API call fails.
    """
    # 1. Read OAuth token
    oauth_token = _read_oauth_token()

    # 2. Call the OAuth usage API
    usage_url = f"{base_url.rstrip('/')}/api/oauth/usage"
    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "anthropic-beta": CLAUDE_BETA_HEADER,
    }

    def _sync_fetch() -> dict:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(usage_url, headers=headers, timeout=15)
        if resp.status_code in (401, 403):
            raise RuntimeError(
                "Claude API returned 401/403. Token may be expired. "
                "Try re-running `claude login`."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Claude API Error (HTTP {resp.status_code}): {resp.text[:500]}"
            )
        return resp.json()

    try:
        data = await asyncio.to_thread(_sync_fetch)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Claude API request failed: {exc}") from exc

    # 3. Parse and return
    return _parse_usage_response(data)