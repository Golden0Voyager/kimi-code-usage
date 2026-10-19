"""
Claude subscription quota provider.

Reads the Claude Code OAuth token — from the macOS login keychain, or from
``~/.claude/.credentials.json`` — and calls the Anthropic OAuth usage endpoint
to retrieve subscription usage limits.

The provider is **disabled by default** — enable it with
``CLAUDE_ENABLED=true`` or ``claude.enabled: true`` in
``~/.kimi-usage/config.json``.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime
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

#: Keychain item Claude Code uses on macOS for its OAuth credentials.
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _is_macos() -> bool:
    """True on macOS, where Claude Code keeps credentials in the login keychain."""
    return sys.platform == "darwin"


def _extract_access_token(creds: Any) -> str | None:
    """Pull the OAuth access token out of a decoded credentials document.

    Claude Code stores ``claudeAiOauth`` as an *object*::

        {"claudeAiOauth": {"accessToken": ..., "refreshToken": ...,
                           "expiresAt": ..., "scopes": [...]}}

    Hand-written files sometimes store the bare token under ``claudeAiOauth``
    instead, so both shapes are accepted, plus a top-level token as a last
    resort.
    """
    if not isinstance(creds, Mapping):
        return None

    oauth = creds.get("claudeAiOauth")
    if isinstance(oauth, Mapping):
        for key in ("accessToken", "access_token"):
            token = oauth.get(key)
            if isinstance(token, str) and token:
                return token
    elif isinstance(oauth, str) and oauth:
        return oauth

    for key in ("accessToken", "access_token", "token"):
        token = creds.get(key)
        if isinstance(token, str) and token:
            return token
    return None


def _read_keychain_token() -> str | None:
    """Read the OAuth token from the macOS login keychain.

    Claude Code stores its credentials as a generic password named
    ``Claude Code-credentials`` whose secret is the same JSON blob that would
    otherwise live in ``~/.claude/.credentials.json``. Every failure mode
    (missing binary, denied access, timeout, non-zero exit, malformed output)
    yields ``None`` so the caller can fall back to the file.
    """
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", CLAUDE_KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if proc.returncode != 0 or not proc.stdout.strip():
        return None

    try:
        return _extract_access_token(json.loads(proc.stdout))
    except json.JSONDecodeError:
        return None


def _read_oauth_token() -> str:
    """Read the Claude Code OAuth token.

    Tries, in order:
    1. The macOS login keychain (``Claude Code-credentials``) — where Claude
       Code actually stores credentials on macOS.
    2. ``~/.claude/.credentials.json`` — the Linux / legacy location.
    3. The ``CLAUDE_CODE_OAUTH_TOKEN`` or ``CLAUDE_USAGE_OAUTH_TOKEN`` env var.
    """
    if _is_macos():
        token = _read_keychain_token()
        if token:
            return token

    if CLAUDE_CREDENTIALS_PATH.exists():
        try:
            with open(CLAUDE_CREDENTIALS_PATH, encoding="utf-8") as f:
                creds = json.load(f)
            token = _extract_access_token(creds)
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    for env_var in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_USAGE_OAUTH_TOKEN"):
        env_token = os.getenv(env_var)
        if env_token:
            return env_token

    raise FileNotFoundError(
        f"Claude OAuth token not found in the macOS keychain "
        f"({CLAUDE_KEYCHAIN_SERVICE}), at {CLAUDE_CREDENTIALS_PATH}, "
        "or in the CLAUDE_CODE_OAUTH_TOKEN env var. "
        "Make sure you have logged in with `claude` CLI first."
    )


def _is_lang_zh() -> bool:
    return "zh" in os.getenv("LANG", "en").lower()


def _normalize_utilization(raw: Any) -> float | None:
    """Convert an OAuth ``utilization`` value into a 0-100 percentage.

    The usage endpoint reports percentages (``15.0`` means 15%). A handful of
    builds return strictly fractional values instead, so ``0 < v < 1`` is
    treated as a fraction. Anything outside 0-100 is clamped.

    Returns ``None`` when the value cannot be interpreted as a number.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if 0.0 < value < 1.0:
        value *= 100.0
    return min(100.0, max(0.0, value))


def _format_reset_at(raw: Any) -> str | None:
    """Render an ISO-8601 ``resets_at`` timestamp as local ``YYYY-MM-DD HH:MM``.

    Unparseable strings are passed through untouched; non-strings are dropped.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        reset = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if reset.tzinfo is not None:
        reset = reset.astimezone()
    return reset.strftime("%Y-%m-%d %H:%M")


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
            if utilization is None:
                continue

            pct = _normalize_utilization(utilization)
            if pct is None:
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
                    reset_at=_format_reset_at(window.get("resets_at")),
                    unit="%",
                )
            )

    # Fallback if no windows were parsed
    if not results:
        raw_keys = ", ".join(str(k) for k in data)
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
