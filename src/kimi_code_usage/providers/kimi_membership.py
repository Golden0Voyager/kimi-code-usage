import asyncio
import json
import os
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import aiohttp

from . import ProviderUsage
from .webbridge import get_webbridge_status, last_webbridge_start_error

_KIMI_CLI_CREDENTIALS_PATH = os.path.expanduser("~/.kimi-code/credentials/kimi-code.json")
_KIMI_OAUTH_USAGES_URL = "https://api.kimi.com/coding/v1/usages"
_OAUTH_TOKEN_EXPIRY_BUFFER_SECONDS = 300


def _load_token_state() -> tuple[str | None, str]:
    """Read the Kimi Code CLI OAuth token, reporting why it is unusable.

    Returns `(token, "")` on success, otherwise `(None, reason)` where `reason`
    is a short human-readable explanation the caller can surface in the UI.
    """
    try:
        with open(_KIMI_CLI_CREDENTIALS_PATH) as f:
            data = json.load(f)
    except OSError:
        return None, "no Kimi CLI credential file"
    except json.JSONDecodeError:
        return None, "credential file is not readable JSON"
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        return None, "credential file has no access_token"
    expires_at = data.get("expires_at")
    if isinstance(expires_at, (int, float)) and expires_at - _OAUTH_TOKEN_EXPIRY_BUFFER_SECONDS <= time.time():
        return None, f"access token expired at {datetime.fromtimestamp(expires_at):%Y-%m-%d %H:%M}"
    return token, ""


def load_kimi_cli_access_token() -> str | None:
    """Return a non-expired Kimi Code CLI OAuth access token, or None.

    The token is read from the credential file produced by `kimi login`. If the
    file is missing, unreadable, or the token is expired, returns None so the
    caller can fall back to another data source (e.g. WebBridge).

    Kept as a thin wrapper over `_load_token_state()` for backward
    compatibility (and existing tests); production callers that need the
    failure reason use `_load_token_state()` directly.
    """
    return _load_token_state()[0]


def _to_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _total_quota_reset_at(total: Mapping[str, Any]) -> str | None:
    raw = total.get("resetTime") or total.get("reset_at") or total.get("reset_time")
    if not raw:
        return None
    try:
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(raw, tz=UTC)
        else:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


async def fetch_monthly_usage_from_oauth(*, lang_zh: bool) -> tuple[ProviderUsage | None, str]:
    """Fetch the monthly membership quota via the Kimi Code CLI OAuth token.

    Uses the same `/usages` endpoint as the API-key path but authenticated with
    the logged-in CLI credential. Returns `(None, reason)` when no token is
    available or the response does not expose a `totalQuota`, so the caller can
    explain why it fell back to WebBridge.
    """
    token, reason = _load_token_state()
    if not token:
        return None, reason

    headers = {"Authorization": f"Bearer {token}", "User-Agent": "KimiCLI/1.6"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(_KIMI_OAUTH_USAGES_URL, headers=headers) as resp:
                if resp.status != 200:
                    return None, f"HTTP {resp.status}"
                payload = await resp.json()
    except (aiohttp.ClientError, TimeoutError) as exc:
        return None, f"request failed: {exc}"

    if not isinstance(payload, Mapping):
        return None, "response has no totalQuota"
    total = payload.get("totalQuota")
    if not isinstance(total, Mapping):
        return None, "response has no totalQuota"
    used = _to_int(total.get("used"))
    limit = _to_int(total.get("limit"))
    if used is None or limit is None or limit <= 0:
        return None, "response has no totalQuota"

    return ProviderUsage(
        provider="kimi",
        label="月度额度" if lang_zh else "Monthly Credits",
        used=float(used),
        limit=float(limit),
        remaining=float(limit - used),
        percent=used / limit * 100,
        reset_at=_total_quota_reset_at(total),
        unit="%",
    ), ""


class MonthlyUsageUnavailableError(Exception):
    """A recoverable failure while reading the local Kimi subscription page."""


MonthlyUsageUnavailable = MonthlyUsageUnavailableError


_BRIDGE_URL = "http://127.0.0.1:10086/command"
_SUBSCRIPTION_URL = "https://www.kimi.com/membership/subscription?tab=quota"
_SESSION = "kimi-usage"
_SNAPSHOT_ATTEMPTS = 8
_SNAPSHOT_INTERVAL_SECONDS = 1.0


def _webbridge_unavailable_message() -> str:
    status = get_webbridge_status()
    if not status.installed:
        return "Kimi WebBridge is not installed."
    start_error = last_webbridge_start_error()
    if not status.running:
        if start_error:
            return f"Kimi WebBridge failed to start: {start_error}"
        if status.detail:
            return f"Kimi WebBridge status check failed: {status.detail}"
        return "Kimi WebBridge daemon is not running."
    if not status.extension_connected:
        return (
            "Kimi WebBridge browser extension is not connected; "
            "open the browser extension."
        )
    return status.detail or "Kimi WebBridge command failed."


def _flatten_names(node: Any) -> list[str]:
    if isinstance(node, list):
        return [name for item in node for name in _flatten_names(item)]
    if not isinstance(node, Mapping):
        return []

    names = [str(node["name"])] if isinstance(node.get("name"), str) else []
    return names + _flatten_names(node.get("children", []))


def parse_monthly_usage_snapshot(
    snapshot: Mapping[str, Any], *, lang_zh: bool
) -> ProviderUsage | None:
    names = _flatten_names(snapshot.get("tree", []))
    start = next(
        (i for i, value in enumerate(names) if value in {"用量进度", "Usage Progress"}),
        None,
    )
    if start is None:
        return None

    end = next(
        (
            i
            for i, value in enumerate(names[start + 1 :], start + 1)
            if value in {"赠送额度", "Bonus Credits"}
        ),
        len(names),
    )
    card = names[start:end]
    total = next(
        (i for i, value in enumerate(card) if value in {"总使用量", "Total Usage"}),
        None,
    )
    if total is None:
        return None

    percent = next(
        (
            re.fullmatch(r"(\d+(?:\.\d+)?)%", value)
            for value in card[total + 1 :]
            if re.fullmatch(r"(\d+(?:\.\d+)?)%", value)
        ),
        None,
    )
    if percent is None:
        return None

    used = float(percent.group(1))
    reset = next(
        (
            re.search(r"(\d{4}-\d{2}-\d{2}).*(?:后重置|reset)", value, re.I)
            for value in card[total + 1 :]
            if re.search(r"\d{4}-\d{2}-\d{2}.*(?:后重置|reset)", value, re.I)
        ),
        None,
    )
    return ProviderUsage(
        provider="kimi",
        label="月度额度" if lang_zh else "Monthly Credits",
        used=used,
        limit=100.0,
        remaining=100.0 - used,
        percent=used,
        reset_at=reset.group(1) if reset else None,
        unit="%",
    )


async def _bridge_command(action: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = {"action": action, "args": dict(args), "session": _SESSION}
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(_BRIDGE_URL, json=payload) as response:
                if response.status != 200:
                    raise MonthlyUsageUnavailable(_webbridge_unavailable_message())
                data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise MonthlyUsageUnavailable(_webbridge_unavailable_message()) from exc
    if not isinstance(data, Mapping) or not data.get("ok"):
        raise MonthlyUsageUnavailable(_webbridge_unavailable_message())
    return data


async def fetch_monthly_usage_from_webbridge(*, lang_zh: bool) -> ProviderUsage:
    try:
        found = await _bridge_command(
            "find_tab", {"url": _SUBSCRIPTION_URL, "active": False}
        )
        opened = not bool((found.get("data") or {}).get("success"))
    except MonthlyUsageUnavailable:
        opened = True
    if opened:
        await _bridge_command(
            "navigate",
            {"url": _SUBSCRIPTION_URL, "newTab": True, "group_title": "Kimi Usage"},
        )
    try:
        for attempt in range(_SNAPSHOT_ATTEMPTS):
            snapshot = await _bridge_command("snapshot", {})
            data = snapshot.get("data")
            row = parse_monthly_usage_snapshot(
                data if isinstance(data, Mapping) else {}, lang_zh=lang_zh
            )
            if row is not None:
                row.label = "月度额度（网页）" if lang_zh else "Monthly Credits (web)"
                return row
            if attempt < _SNAPSHOT_ATTEMPTS - 1:
                await asyncio.sleep(_SNAPSHOT_INTERVAL_SECONDS)
        raise MonthlyUsageUnavailable(
            "Kimi monthly usage was not found; log in and open the Subscription page."
        )
    finally:
        if opened:
            await _bridge_command("close_tab", {})
