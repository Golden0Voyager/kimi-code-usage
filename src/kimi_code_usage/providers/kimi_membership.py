import re
from collections.abc import Mapping
from typing import Any

from . import ProviderUsage


class MonthlyUsageUnavailable(Exception):
    """A recoverable failure while reading the local Kimi subscription page."""


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
