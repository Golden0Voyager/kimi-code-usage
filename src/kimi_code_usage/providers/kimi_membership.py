import asyncio
import re
from collections.abc import Mapping
from typing import Any

import aiohttp

from . import ProviderUsage


class MonthlyUsageUnavailableError(Exception):
    """A recoverable failure while reading the local Kimi subscription page."""


MonthlyUsageUnavailable = MonthlyUsageUnavailableError


_BRIDGE_URL = "http://127.0.0.1:10086/command"
_SUBSCRIPTION_URL = "https://www.kimi.com/membership/subscription?tab=quota"
_SESSION = "kimi-usage"


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
                    raise MonthlyUsageUnavailable(
                        "Kimi WebBridge is unavailable; start it and open the browser extension."
                    )
                data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise MonthlyUsageUnavailable(
            "Kimi WebBridge is unavailable; start it and open the browser extension."
        ) from exc
    if not isinstance(data, Mapping) or not data.get("ok"):
        raise MonthlyUsageUnavailable(
            "Kimi WebBridge is unavailable; start it and open the browser extension."
        )
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
        for attempt in range(3):
            snapshot = await _bridge_command("snapshot", {})
            data = snapshot.get("data")
            row = parse_monthly_usage_snapshot(
                data if isinstance(data, Mapping) else {}, lang_zh=lang_zh
            )
            if row is not None:
                return row
            if attempt < 2:
                await asyncio.sleep(0.5)
        raise MonthlyUsageUnavailable(
            "Kimi monthly usage was not found; log in and open the Subscription page."
        )
    finally:
        if opened:
            await _bridge_command("close_tab", {})
