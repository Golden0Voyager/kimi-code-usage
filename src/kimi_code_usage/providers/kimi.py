import aiohttp
from datetime import datetime, timedelta
from typing import Any, List, Mapping, Optional, Sequence, Tuple, cast
from . import ProviderUsage

def _to_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def _get_reset_info(data: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    reset_at = data.get("resetTime") or data.get("reset_at") or data.get("reset_time")
    if reset_at:
        try:
            if isinstance(reset_at, (int, float)):
                dt = datetime.fromtimestamp(reset_at)
            else:
                dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00")).astimezone()

            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            diff = dt - now
            if diff.total_seconds() <= 0:
                return dt.strftime("%m-%d %H:%M"), "0m"
            days = diff.days
            hours, rem = divmod(diff.seconds, 3600)
            minutes, _ = divmod(rem, 60)
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            parts.append(f"{minutes}m")
            return dt.strftime("%m-%d %H:%M"), " ".join(parts)
        except Exception:
            pass

    reset_in = _to_int(data.get("reset_in"))
    if reset_in is not None:
        dt = datetime.now() + timedelta(seconds=reset_in)
        hours, rem = divmod(reset_in, 3600)
        minutes, _ = divmod(rem, 60)
        return dt.strftime("%m-%d %H:%M"), f"{hours}h {minutes}m"
    return None

def _limit_label(window: Mapping[str, Any], idx: int) -> str:
    duration = _to_int(window.get("duration"))
    time_unit = str(window.get("time_unit") or "").upper()
    if duration and time_unit:
        if "HOUR" in time_unit:
            return f"{duration}h Limit"
        if "DAY" in time_unit:
            return f"{duration}d Limit"
    return f"Limit #{idx + 1}"

class KimiRow:
    def __init__(self, label: str, used: int, limit: int, reset_at: Optional[str] = None, countdown: Optional[str] = None):
        self.label = label
        self.used = used
        self.limit = limit
        self.reset_at = reset_at
        self.countdown = countdown

def _to_usage_row(data: Mapping[str, Any], default_label: str) -> Optional[KimiRow]:
    limit = _to_int(data.get("limit") or data.get("limit_amount"))
    used = _to_int(data.get("used") or data.get("used_amount"))
    if used is None:
        remaining = _to_int(data.get("remaining"))
        if remaining is not None and limit is not None:
            used = limit - remaining
    if used is None and limit is None:
        return None
    reset_info = _get_reset_info(data)
    reset_at, countdown = reset_info if reset_info else (None, None)
    return KimiRow(
        label=str(data.get("name") or data.get("title") or data.get("model_name") or default_label),
        used=used or 0,
        limit=limit or 0,
        reset_at=reset_at,
        countdown=countdown,
    )

def _parse_usage_payload(payload: Mapping[str, Any]) -> Tuple[Optional[KimiRow], List[KimiRow]]:
    summary = None
    limits = []

    data_list = payload.get("data")
    if isinstance(data_list, Sequence):
        for item in data_list:
            if not isinstance(item, Mapping):
                continue
            label = "Weekly Usage" if item.get("model_name") == "all" else "Limit"
            row = _to_usage_row(item, default_label=label)
            if row:
                if item.get("model_name") == "all":
                    summary = row
                else:
                    limits.append(row)
    else:
        usage = payload.get("usage")
        if isinstance(usage, Mapping):
            summary = _to_usage_row(cast(Mapping, usage), default_label="Weekly Usage")
        raw_limits = payload.get("limits")
        if isinstance(raw_limits, Sequence):
            for idx, item in enumerate(raw_limits):
                if not isinstance(item, Mapping):
                    continue
                detail = item.get("detail") if isinstance(item.get("detail"), Mapping) else item
                window = item.get("window") if isinstance(item.get("window"), Mapping) else {}
                row = _to_usage_row(detail, default_label=_limit_label(window, idx))
                if row:
                    limits.append(row)

    return summary, limits

async def fetch_kimi_usage(api_key: str, base_url: str) -> List[ProviderUsage]:
    url = base_url.rstrip("/") + "/usages"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Authorization": f"Bearer {api_key}"}) as resp:
            if resp.status != 200:
                fallback_url = base_url.rstrip("/") + "/usage"
                async with session.get(fallback_url, headers={"Authorization": f"Bearer {api_key}"}) as f_resp:
                    if f_resp.status != 200:
                        text = await f_resp.text()
                        raise Exception(f"API Error {f_resp.status}: {text}")
                    payload = await f_resp.json()
            else:
                payload = await resp.json()

    summary, limits = _parse_usage_payload(payload)
    rows = ([summary] if summary else []) + limits

    res = []
    for r in rows:
        pct = (r.used / r.limit * 100) if r.limit > 0 else 0.0
        rem = float(r.limit - r.used)
        res.append(ProviderUsage(
            provider="kimi",
            label=r.label,
            used=float(r.used),
            limit=float(r.limit),
            remaining=rem,
            percent=pct,
            reset_at=r.reset_at,
            countdown=r.countdown,
            unit="%"
        ))
    return res
