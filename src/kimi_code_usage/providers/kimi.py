import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, cast

import aiohttp

from . import ProviderUsage


def _to_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def _get_reset_info(data: Mapping[str, Any]) -> tuple[str, str] | None:
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
    time_unit = str(window.get("timeUnit") or window.get("time_unit") or "").upper()
    if duration is not None:
        if "MINUTE" in time_unit:
            if duration >= 60 and duration % 60 == 0:
                return f"{duration // 60}h Limit"
            return f"{duration}m Limit"
        if "HOUR" in time_unit:
            return f"{duration}h Limit"
        if "DAY" in time_unit:
            return f"{duration}d Limit"
        if "MONTH" in time_unit:
            return f"{duration}mo Limit"
        return f"{duration}s Limit"
    return f"Limit #{idx + 1}"

class KimiRow:
    def __init__(self, label: str, used: int, limit: int, reset_at: str | None = None, countdown: str | None = None):
        self.label = label
        self.used = used
        self.limit = limit
        self.reset_at = reset_at
        self.countdown = countdown

def _to_usage_row(data: Mapping[str, Any], default_label: str) -> KimiRow | None:
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

def _parse_usage_payload(payload: Mapping[str, Any]) -> tuple[KimiRow | None, list[KimiRow]]:
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

_KIMI_USER_AGENT = "KimiCLI/1.6"

def _kimi_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": _KIMI_USER_AGENT,
    }

_KIMI_LANG_IS_ZH = "zh" in os.getenv("LANG", "en").lower()

def _kimi_error_hint(status: int, zh: bool | None = None) -> str:
    if zh is None:
        zh = _KIMI_LANG_IS_ZH
    if zh:
        hints = {
            401: (
                "Kimi Code API 认证失败（401）。\n"
                "  ▸ 请确认你使用的是 Kimi Code 平台（Coding Plan）的 API Key，格式为 sk-kimi-xxx\n"
                "  ▸ 请勿使用 Kimi 开放平台（platform.kimi.com）的 sk-xxx 类型密钥\n"
                "  ▸ 如需获取正确的 Key，请前往 Kimi Code 控制台创建\n"
                "  ▸ 环境变量：KIMI_API_KEY 或 KIMI_CODING_API_KEY"
            ),
            404: (
                "未找到 Kimi Code API 用量接口（404）。\n"
                "  ▸ 请确认 KIMI_BASE_URL/baseUrl 是 https://api.kimi.com/coding/v1\n"
                "  ▸ 请勿使用 Kimi 开放平台地址（https://api.moonshot.cn/v1 或 platform.kimi.com）\n"
                "  ▸ 请确认 API Key 来自 Kimi Code 平台（Coding Plan），格式为 sk-kimi-xxx"
            ),
            403: "Kimi Code API 拒绝访问（403），请检查 API Key 是否有权限访问用量接口。",
            429: "Kimi Code API 请求过于频繁（429），请稍后重试。",
        }
        return hints.get(status, f"Kimi Code API 返回错误 {status}")
    hints = {
        401: (
            "Kimi Code API authentication failed (401).\n"
            "  ▸ Make sure you are using a Kimi Code Platform (Coding Plan) API Key (format: sk-kimi-xxx)\n"
            "  ▸ Do NOT use a Kimi Open Platform (platform.kimi.com / api.moonshot.cn) API Key (format: sk-xxx)\n"
            "  ▸ Get the correct key from Kimi Code Console\n"
            "  ▸ Environment variables: KIMI_API_KEY or KIMI_CODING_API_KEY"
        ),
        404: (
            "Kimi Code API usage endpoint was not found (404).\n"
            "  ▸ Make sure KIMI_BASE_URL/baseUrl is https://api.kimi.com/coding/v1\n"
            "  ▸ Do NOT use the Kimi Open Platform base URL (https://api.moonshot.cn/v1 or platform.kimi.com)\n"
            "  ▸ Make sure the API Key is from Kimi Code Platform (Coding Plan), format: sk-kimi-xxx"
        ),
        403: "Kimi Code API access denied (403). Check if your API Key has permission to access the usage endpoint.",
        429: "Kimi Code API rate limited (429). Please retry later.",
    }
    return hints.get(status, f"Kimi Code API returned error {status}")

async def fetch_kimi_usage(api_key: str, base_url: str, management_key: str | None = None) -> list[ProviderUsage]:
    url = base_url.rstrip("/") + "/usages"
    headers = _kimi_headers(api_key)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                payload = await resp.json()
            elif resp.status == 404:
                fallback_url = base_url.rstrip("/") + "/usage"
                async with session.get(fallback_url, headers=headers) as f_resp:
                    if f_resp.status != 200:
                        text = await f_resp.text()
                        hint = _kimi_error_hint(f_resp.status)
                        raise Exception(f"{hint}\n  Original: API Error {f_resp.status}: {text}")
                    payload = await f_resp.json()
            else:
                text = await resp.text()
                hint = _kimi_error_hint(resp.status)
                raise Exception(f"{hint}\n  Original: API Error {resp.status}: {text}")

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
