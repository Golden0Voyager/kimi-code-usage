"""
Codex / ChatGPT Plus subscription quota provider.

Reads OAuth tokens from the local Codex CLI auth file
(``~/.codex/auth.json``) and calls the ChatGPT backend API to
retrieve subscription usage limits (weekly window, 5‑hour window).

The provider is **disabled by default** — enable it with
``CODEX_ENABLED=true`` or ``codex.enabled: true`` in
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

CODEX_AUTH_PATH = Path.home() / ".codex" / "auth.json"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"

# ---------------------------------------------------------------------------
# Auth file helpers
# ---------------------------------------------------------------------------


def _read_auth() -> dict[str, Any]:
    """Read and validate the Codex auth file."""
    if not CODEX_AUTH_PATH.exists():
        raise FileNotFoundError(
            f"Codex auth file not found at {CODEX_AUTH_PATH}. "
            "Make sure you have logged in with `codex login` first."
        )
    try:
        with open(CODEX_AUTH_PATH, encoding="utf-8") as f:
            auth: dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Failed to read Codex auth file: {exc}") from exc

    auth_mode = auth.get("auth_mode")
    if auth_mode != "chatgpt":
        raise RuntimeError(
            f"Codex auth mode is '{auth_mode}', expected 'chatgpt'. "
            "Make sure you are logged in with ChatGPT (`codex login`)."
        )

    tokens: Any = auth.get("tokens", {})
    if not isinstance(tokens, Mapping):
        raise RuntimeError("Codex auth file has invalid 'tokens' field.")

    access_token: str | None = tokens.get("access_token")
    account_id: str | None = tokens.get("account_id")
    refresh_token: str | None = tokens.get("refresh_token")

    if not access_token or not account_id:
        raise RuntimeError(
            "Codex auth file is missing 'access_token' or 'account_id'. "
            "Try re-running `codex login`."
        )
    return {
        "access_token": access_token,
        "account_id": account_id,
        "refresh_token": refresh_token,
    }


def _write_auth(auth_data: dict[str, Any]) -> None:
    """Write updated token data back to the Codex auth file."""
    try:
        existing: dict[str, Any] = {}
        if CODEX_AUTH_PATH.exists():
            with open(CODEX_AUTH_PATH, encoding="utf-8") as f:
                existing = json.load(f)
        existing.setdefault("tokens", {}).update(auth_data)
        with open(CODEX_AUTH_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise RuntimeError(f"Failed to write updated tokens to auth file: {exc}") from exc


async def _refresh_access_token(refresh_token: str) -> dict[str, str]:
    """Exchange a refresh token for a new access token via OAuth."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CODEX_CLIENT_ID,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    def _sync_refresh() -> dict[str, str]:
        scraper = cloudscraper.create_scraper()
        resp = scraper.post(CODEX_TOKEN_URL, data=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Token refresh failed (HTTP {resp.status_code}): {resp.text}"
            )
        return resp.json()

    body = await asyncio.to_thread(_sync_refresh)

    new_access = body.get("access_token")
    new_refresh = body.get("refresh_token", refresh_token)
    if not new_access:
        raise RuntimeError("Token refresh response missing 'access_token'.")

    return {"access_token": new_access, "refresh_token": new_refresh}


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _is_lang_zh() -> bool:
    return "zh" in os.getenv("LANG", "en").lower()


def _parse_usage_response(data: Mapping[str, Any]) -> list[ProviderUsage]:
    """Parse the ChatGPT backend usage response into ``ProviderUsage`` rows.

    Handles several possible response shapes so the provider is resilient to
    API format changes.
    """
    results: list[ProviderUsage] = []
    is_zh = _is_lang_zh()

    # --- Plan type (text row) ---
    plan_type: str | None = data.get("plan_type")
    if not plan_type:
        plan_type = data.get("planType")
    if plan_type:
        plan_label = "订阅计划" if is_zh else "Plan"
        results.append(
            ProviderUsage(
                provider="codex",
                label=plan_label,
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value=plan_type.capitalize() if plan_type != "plus" else "ChatGPT Plus",
            )
        )

    # --- Status (text row) ---
    status: str | None = data.get("status")
    if status:
        status_label = "状态" if is_zh else "Status"
        results.append(
            ProviderUsage(
                provider="codex",
                label=status_label,
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value=status.capitalize(),
            )
        )

    # --- Limits (progress bars) ---
    # Try several possible locations for limit data.
    limits: list[Mapping[str, Any]] = []

    # Shape 1: top-level "limits" array
    raw_limits = data.get("limits")
    if isinstance(raw_limits, list):
        limits = raw_limits

    # Shape 2: top-level "usage" object with limit sub-keys
    usage = data.get("usage")
    if isinstance(usage, Mapping) and not limits:
        for window_key in ("weekly", "five_hour", "5h", "daily", "monthly"):
            window_data = usage.get(window_key)
            if isinstance(window_data, Mapping):
                # Preserve the key name as the window name
                if "window" not in window_data and "name" not in window_data and "period" not in window_data:
                    window_data = {**window_data, "window": window_key}
                limits.append(window_data)

    # Shape 3: flat top-level keys with usage/limit
    if not limits:
        for key in ("weekly_limit", "five_hour_limit", "daily_limit", "monthly_limit"):
            val = data.get(key)
            if isinstance(val, Mapping):
                limits.append(val)

    # Shape 4: "usage_limits" array
    if not limits:
        raw_ul = data.get("usage_limits") or data.get("usageLimits")
        if isinstance(raw_ul, list):
            limits = raw_ul

    # Shape 5: RateLimitStatusPayload (Codex backend OpenAPI format)
    rate_limit = data.get("rate_limit")
    if isinstance(rate_limit, Mapping) and not limits:
        primary = rate_limit.get("primary_window")
        secondary = rate_limit.get("secondary_window")
        if isinstance(primary, Mapping) and "used_percent" in primary:
            # Determine window label from limit_window_seconds
            window_seconds = primary.get("limit_window_seconds", 0)
            if window_seconds >= 604800:  # 7+ days
                limits.append({**primary, "window": "weekly"})
            elif window_seconds >= 18000:  # 5+ hours
                limits.append({**primary, "window": "5h"})
            else:
                limits.append({**primary, "window": str(window_seconds) + "s"})
        if isinstance(secondary, Mapping) and "used_percent" in secondary:
            limits.append({**secondary, "window": "5h"})

    # Shape 6: spend_control.individual_limit
    spend_control = data.get("spend_control")
    if isinstance(spend_control, Mapping):
        individual = spend_control.get("individual_limit")
        if isinstance(individual, Mapping):
            limits.append({**individual, "window": "spend"})

    # Shape 7: credits
    credits = data.get("credits")
    if isinstance(credits, Mapping):
        balance = credits.get("balance")
        if isinstance(balance, str):
            results.append(
                ProviderUsage(
                    provider="codex",
                    label="额度余额" if is_zh else "Credit Balance",
                    used=0.0,
                    limit=None,
                    remaining=None,
                    percent=None,
                    reset_at=None,
                    unit="text",
                    text_value=f"${balance}" if balance else "N/A",
                )
            )

    for limit_entry in limits:
        if not isinstance(limit_entry, Mapping):
            continue

        used = _to_float(limit_entry.get("used") or limit_entry.get("used_amount") or limit_entry.get("usage"))
        limit = _to_float(limit_entry.get("limit") or limit_entry.get("limit_amount") or limit_entry.get("total"))
        used_pct = _to_float(limit_entry.get("used_percent"))
        window = str(limit_entry.get("window") or limit_entry.get("name") or limit_entry.get("period") or "")

        # Handle RateLimitWindowSnapshot format: only used_percent, no used/limit
        if used is None and limit is None and used_pct is not None:
            used = used_pct
            limit = 100.0

        if used is not None and limit is not None and limit > 0:
            pct = used / limit * 100
            remaining = max(0.0, limit - used)

            # Determine label
            wl = window.lower()
            if "week" in wl or "7d" in wl or "7" in wl:
                label = "周用量" if is_zh else "Weekly Usage"
            elif "5" in wl or "hour" in wl or "5h" in wl:
                label = "5小时限额" if is_zh else "5h Limit"
            elif "day" in wl or "daily" in wl or "24" in wl:
                label = "日用量" if is_zh else "Daily Usage"
            elif "month" in wl:
                label = "月用量" if is_zh else "Monthly Usage"
            elif "spend" in wl:
                label = "支出限额" if is_zh else "Spend Limit"
            else:
                label = str(limit_entry.get("label") or window or "限额" if is_zh else "Limit")

            results.append(
                ProviderUsage(
                    provider="codex",
                    label=label,
                    used=used,
                    limit=limit,
                    remaining=remaining,
                    percent=pct,
                    reset_at=None,
                    unit="%",
                )
            )

    # --- Fallback: show raw data as text ---
    if not results:
        # If we couldn't parse anything useful, show the raw JSON keys
        raw_keys = ", ".join(str(k) for k in data)
        results.append(
            ProviderUsage(
                provider="codex",
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


def _to_float(val: Any) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------


async def fetch_codex_usage(
    api_key: str, base_url: str, management_key: str | None = None
) -> list[ProviderUsage]:
    """Fetch ChatGPT Plus subscription usage from the Codex backend API.

    Parameters
    ----------
    api_key : str
        Ignored — the provider reads the Codex auth file directly.
    base_url : str
        Base URL for the ChatGPT backend API
        (default: ``https://chatgpt.com/backend-api``).
    management_key : str | None
        Ignored.

    Raises
    ------
    FileNotFoundError
        If ``~/.codex/auth.json`` is missing.
    RuntimeError
        If the auth file is invalid or the API call fails.
    """
    # 1. Read auth
    auth = _read_auth()
    access_token = auth["access_token"]
    account_id = auth["account_id"]
    refresh_token = auth.get("refresh_token")

    # 2. Call the usage API (use /wham/usage for cloudscraper bypass)
    usage_url = f"{base_url.rstrip('/')}/wham/usage"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ChatGPT-Account-Id": account_id,
    }

    def _sync_fetch() -> dict:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(usage_url, headers=headers, timeout=15)
        if resp.status_code == 401 and refresh_token:
            raise RuntimeError(
                "Codex API returned 401. Token may be expired. "
                "Try re-running `codex login`."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Codex API Error (HTTP {resp.status_code}): {resp.text[:500]}"
            )
        return resp.json()

    try:
        data = await asyncio.to_thread(_sync_fetch)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Codex API request failed: {exc}") from exc

    # 3. Parse and return
    return _parse_usage_response(data)
