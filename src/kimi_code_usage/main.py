import argparse
import asyncio
import json
import os
import select as _select_module
import sys

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from kimi_code_usage.config import DEFAULT_CONFIG_PATH, AppConfig, ConfigResolver, save_theme
from kimi_code_usage.providers import DailyUsage, ModelUsage, ProviderUsage, dispatch_all
from kimi_code_usage.server import run_server

# --- i18n ---
LANG = os.getenv("LANG", "en")
IS_ZH = "zh" in LANG.lower()

L_EN = {
    "title": "AI Quota Monitor",
    "weekly_limit": "Weekly Usage",
    "limit_fallback": "Limit",
    "remaining": "remaining",
    "countdown": "Countdown",
    "reset": "Reset",
    "no_data": "No usage data found or no providers configured.",
    "error_api": "API Error",
}

_SHORT = {
    "anthropic": "Anthropic", "openai": "OpenAI API",
    "openrouter": "Openrouter",    "kimi": "Kimi",
    "codex": "ChatGPT+", "claude": "Claude",
}


L_ZH = {
    "title": "AI 用量配额监控",
    "weekly_limit": "周用量限额",
    "limit_fallback": "限额",
    "remaining": "剩余",
    "countdown": "重置倒计时",
    "reset": "重置时间",
    "no_data": "未找到用量数据，或未配置任何服务商。",
    "error_api": "API 错误",
}



L = L_ZH if IS_ZH else L_EN

_PROVIDER_SETUP_HELP = {
    "kimi": {
        "name": "Kimi Code",
        "key_envs": ("KIMI_API_KEY", "KIMI_CODING_API_KEY"),
        "base_env": "KIMI_BASE_URL",
        "default_url": "https://api.kimi.com/coding/v1",
        "note_en": "Use a Kimi Code / Coding Plan key (sk-kimi-...). Do not use https://api.moonshot.cn/v1.",
        "note_zh": "使用 Kimi Code / Coding Plan 密钥（sk-kimi-...），不要使用 https://api.moonshot.cn/v1。",
    },
    "openai": {
        "name": "OpenAI API",
        "key_envs": ("OPENAI_API_KEY",),
        "base_env": "OPENAI_BASE_URL",
        "default_url": "https://api.openai.com",
        "note_en": "OpenAI Platform API billing (requires Org Admin key). Not ChatGPT Plus subscription.",
        "note_zh": "OpenAI 平台 API 账单（需 Org Admin 密钥）。不是 ChatGPT Plus 订阅。",
    },
    "anthropic": {
        "name": "Anthropic",
        "key_envs": ("ANTHROPIC_API_KEY",),
        "base_env": "ANTHROPIC_BASE_URL",
        "default_url": "https://api.anthropic.com",
        "note_en": "Use an Anthropic key that can access the usage endpoint.",
        "note_zh": "使用具备用量接口权限的 Anthropic Key。",
    },
    "openrouter": {
        "name": "OpenRouter",
        "key_envs": ("OPENROUTER_API_KEY", "OPENROUTER_ADMIN_KEY"),
        "base_env": "OPENROUTER_BASE_URL",
        "default_url": "https://openrouter.ai/api",
        "note_en": "Set OPENROUTER_MANAGEMENT_KEY or OPENROUTER_ADMIN_KEY for activity details.",
        "note_zh": "如需活动明细，设置 OPENROUTER_MANAGEMENT_KEY 或 OPENROUTER_ADMIN_KEY。",
    },
    "codex": {
        "name": "ChatGPT Plus",
        "key_envs": ("CODEX_ENABLED",),
        "base_env": "CODEX_BASE_URL",
        "default_url": "https://chatgpt.com/backend-api",
        "note_en": "ChatGPT Plus subscription usage. Reads ~/.codex/auth.json. Set CODEX_ENABLED=true to enable.",
        "note_zh": "ChatGPT Plus 订阅用量。读取 ~/.codex/auth.json 本地认证文件。设置 CODEX_ENABLED=true 启用。",
    },
    "claude": {
        "name": "Claude",
        "key_envs": ("CLAUDE_ENABLED",),
        "base_env": "CLAUDE_BASE_URL",
        "default_url": "https://api.anthropic.com",
        "note_en": "Claude subscription usage. Reads ~/.claude/.credentials.json. Set CLAUDE_ENABLED=true to enable.",
        "note_zh": "Claude 订阅用量。读取 ~/.claude/.credentials.json 本地认证文件。设置 CLAUDE_ENABLED=true 启用。",
    },
}



def _get_visual_width(s: str) -> int:
    import unicodedata
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ("W", "F", "A"):
            width += 2
        else:
            width += 1
    return width


def _mask_secret(secret: str | None) -> str:
    if not secret:
        return "missing"
    if len(secret) <= 8:
        return secret[:2] + "..."
    return f"{secret[:7]}...{secret[-4:]}"

def _get_localized_label(label: str, lang_zh: bool = IS_ZH) -> str:
    _L = L_ZH if lang_zh else L_EN

    # 1. Dynamic translations first
    if lang_zh:
        translations = {
            "Credits": "额度",
            "Key Name": "密钥名称",
            "Rate Limit": "速率限制",
            "Usage": "周期已用",
            "周期已用": "周期已用",
            "Free Tier": "免费额度",
            "Limit Reset": "限额重置周期",
            "Expires At": "过期时间",
            "Is Provisioning": "配给密钥",
            "Management Key": "管理密钥",
        }
        if label in translations:
            return translations[label]
    else:
        translations = {
            "额度": "Credits",
            "密钥名称": "Key Name",
            "速率限制": "Rate Limit",
            "周期已用": "Usage",
            "Usage": "Usage",
            "免费额度": "Free Tier",
            "限额重置周期": "Limit Reset",
            "过期时间": "Expires At",
            "配给密钥": "Is Provisioning",
            "管理密钥": "Management Key",
        }
        if label in translations:
            return translations[label]

    # 2. Standard rule replacements
    if label == "Weekly Usage":
        return _L["weekly_limit"]
    if "h Limit" in label:
        h = label.split("h")[0]
        return f"{h}小时限额" if lang_zh else label
    if "d Limit" in label:
        d = label.split("d")[0]
        return f"{d}天限额" if lang_zh else label
    if "mo Limit" in label:
        mo = label.split("mo")[0]
        return f"{mo}个月限额" if lang_zh else label
    if "m Limit" in label:
        m = label.split("m")[0]
        return f"{m}分钟限额" if lang_zh else label
    if "Limit" in label:
        return label.replace("Limit", _L["limit_fallback"])
    return label


def _get_localized_text_value(text_val: str, lang_zh: bool) -> str:
    if not text_val:
        return text_val
    # OpenRouter period usage pattern
    if "Daily: $" in text_val or "今日: $" in text_val:
        import re
        floats = re.findall(r"\d+\.\d+", text_val)
        if len(floats) == 3:
            u_daily, u_weekly, u_monthly = float(floats[0]), float(floats[1]), float(floats[2])
            if lang_zh:
                return f"今日: ${u_daily:.4f} | 本周: ${u_weekly:.4f} | 本月: ${u_monthly:.4f}"
            else:
                return f"Daily: ${u_daily:.4f} | Weekly: ${u_weekly:.4f} | Monthly: ${u_monthly:.4f}"

    # Rate limit localization (e.g., Unlimited/10s <-> 无限制/10秒, 20 req/1s <-> 20次/1秒)
    if lang_zh:
        if text_val.startswith("Unlimited/"):
            interval = text_val.split("/", 1)[1]
            interval_zh = interval.replace("s", "秒").replace("m", "分钟").replace("h", "小时")
            return f"无限制/{interval_zh}"
        elif " req/" in text_val:
            reqs, interval = text_val.split(" req/", 1)
            interval_zh = interval.replace("s", "秒").replace("m", "分钟").replace("h", "小时")
            return f"{reqs}次/{interval_zh}"
    else:
        if text_val.startswith("无限制/"):
            interval = text_val.split("/", 1)[1]
            interval_en = interval.replace("秒", "s").replace("分钟", "m").replace("小时", "h")
            return f"Unlimited/{interval_en}"
        elif "次/" in text_val:
            reqs, interval = text_val.split("次/", 1)
            interval_en = interval.replace("秒", "s").replace("分钟", "m").replace("小时", "h")
            return f"{reqs} req/{interval_en}"

    # Yes/No localization
    if lang_zh:
        if text_val == "Yes":
            return "是"
        if text_val == "No":
            return "否"
    else:
        if text_val == "是":
            return "Yes"
        if text_val == "否":
            return "No"

    return text_val


def _render_setting_view(
    config: "AppConfig",
    visible_providers: set,
    settings_cursor: int = 0,
    lang_zh: bool = False,
) -> Text:
    """Render the settings page for toggling and reordering providers."""
    text = Text()
    title = "面板设置" if lang_zh else "Panel Settings"
    text.append(f"{title}\n\n", style="bold")

    order = config.provider_order
    max_keys = min(len(order), 9)
    for i, p in enumerate(order):
        short = _SHORT.get(p, p[:4].title())
        icon = "●" if p in visible_providers else "○"
        num = i + 1
        cursor = "▸" if i == settings_cursor else " "
        line = f"{cursor} {icon} [{num}] {short}"
        if i == settings_cursor:
            text.append(line, style="bold reverse")
        elif p in visible_providers:
            text.append(line, style="bold")
        else:
            text.append(line, style="dim")
        text.append("\n")

    text.append("\n", style="bold")
    if lang_zh:
        text.append(f"  [1-{max_keys}] 开关面板\n", style="grey62")
        text.append("  [↑/↓] 移动光标\n", style="grey62")
        text.append("  [←/→] 移动选中面板\n", style="grey62")
        text.append("  [s]   返回用量视图\n", style="grey62")
        text.append("  Enter 保存设置\n", style="grey62")
    else:
        text.append(f"  [1-{max_keys}] toggle panels\n", style="grey62")
        text.append("  [↑/↓] move cursor\n", style="grey62")
        text.append("  [←/→] move selected panel\n", style="grey62")
        text.append("  [s]   back to usage\n", style="grey62")
        text.append("  Enter save settings\n", style="grey62")

    return text


def _render_interactive_help(lang_zh: bool, or_metric: str = "requests", days_window: int = 30, provider_count: int = 6) -> Text:
    text = Text()
    title = "交互帮助" if lang_zh else "Interactive Help"
    text.append(f"{title}\n\n", style="bold")
    key_range = f"1-{provider_count}"
    if lang_zh:
        rows = [
            ("q / Ctrl-C", "退出"),
            ("r", "刷新用量"),
            ("h / ?", "显示或隐藏帮助"),
            ("c", "显示或隐藏配置引导"),
            ("s", "面板设置"),
            (key_range, "切换服务商面板"),
            ("l", "切换中英文"),
            ("←/→ 或 [ / ]", "切换主题"),
            ("m", f"切换 OpenRouter 指标（当前：{_metric_label(or_metric, True)}）"),
            ("d", f"切换 OpenRouter 图表窗口（当前：{days_window}d）"),
            ("Enter", "保存主题、语言、可见面板和 OpenRouter 显示偏好"),
        ]
        footer = "再次按 h/? 或 c 可回到用量视图。"
    else:
        rows = [
            ("q / Ctrl-C", "quit"),
            ("r", "refresh usage"),
            ("h / ?", "show or hide help"),
            ("c", "show or hide configuration guide"),
            ("s", "panel settings"),
            (key_range, "toggle provider panels"),
            ("l", "toggle language"),
            ("←/→ or [ / ]", "cycle theme"),
            ("m", f"cycle OpenRouter metric (current: {_metric_label(or_metric, False)})"),
            ("d", f"cycle OpenRouter chart window (current: {days_window}d)"),
            ("Enter", "save theme, language, visible panels, and OpenRouter display preferences"),
        ]
        footer = "Press h/? or c again to return to the usage view."

    for key, desc in rows:
        text.append(f"  {key:<16}", style="bold")
        text.append(f"{desc}\n", style="grey62")
    text.append(f"\n{footer}", style="grey62")
    return text


def _render_config_guide(
    config: AppConfig,
    lang_zh: bool = IS_ZH,
    config_path: str | None = None,
) -> Text:
    text = Text()
    title = "配置引导" if lang_zh else "Configuration Guide"
    path = config_path or str(DEFAULT_CONFIG_PATH)
    text.append(f"{title}\n\n", style="bold")
    if lang_zh:
        text.append(f"配置文件: {path}\n", style="grey62")
        text.append("读取优先级: config.json > 环境变量 / 当前目录 .env > 默认 base URL\n\n", style="grey62")
    else:
        text.append(f"Config file: {path}\n", style="grey62")
        text.append("Resolution order: config.json > environment variables / current .env > default base URL\n\n", style="grey62")

    provider_order = list(config.provider_order)
    for provider_name in _PROVIDER_SETUP_HELP:
        if provider_name not in provider_order:
            provider_order.append(provider_name)

    for provider_name in provider_order:
        help_info = _PROVIDER_SETUP_HELP.get(provider_name)
        if not help_info:
            continue
        p_conf = config.providers.get(provider_name)
        api_key = p_conf.api_key if p_conf else None
        base_url = p_conf.base_url if p_conf and p_conf.base_url else help_info["default_url"]
        enabled = p_conf.enabled if p_conf else True
        status = "enabled" if api_key and enabled else ("disabled" if not enabled else "missing")
        if lang_zh:
            status_label = {"enabled": "已启用", "disabled": "已禁用", "missing": "缺少密钥"}[status]
            text.append(f"{help_info['name']}\n", style="bold")
            text.append(f"  状态: {status_label}\n", style="grey62")
            text.append(f"  Key: {_mask_secret(api_key)}  ({' / '.join(help_info['key_envs'])})\n", style="grey62")
            text.append(f"  Base URL: {base_url}  ({help_info['base_env']})\n", style="grey62")
            text.append(f"  提示: {help_info['note_zh']}\n", style="grey62")
        else:
            text.append(f"{help_info['name']}\n", style="bold")
            text.append(f"  status: {status}\n", style="grey62")
            text.append(f"  key: {_mask_secret(api_key)}  ({' / '.join(help_info['key_envs'])})\n", style="grey62")
            text.append(f"  baseUrl: {base_url}  ({help_info['base_env']})\n", style="grey62")
            text.append(f"  note: {help_info['note_en']}\n", style="grey62")

        if provider_name == "openrouter":
            management_key = p_conf.management_key if p_conf else None
            if lang_zh:
                text.append(
                    f"  管理 Key: {_mask_secret(management_key)}  (OPENROUTER_MANAGEMENT_KEY / OPENROUTER_ADMIN_KEY)\n",
                    style="grey62",
                )
            else:
                text.append(
                    f"  management key: {_mask_secret(management_key)}  (OPENROUTER_MANAGEMENT_KEY / OPENROUTER_ADMIN_KEY)\n",
                    style="grey62",
                )
        text.append("\n")

    if lang_zh:
        text.append(
            "建议把长期配置写入 ~/.kimi-usage/config.json；uvx 每次运行都会读取这个文件。\n",
            style="grey62",
        )
    else:
        text.append(
            "For persistent uvx usage, put long-lived settings in ~/.kimi-usage/config.json.\n",
            style="grey62",
        )
    return text

# (typing already imported at top)

THEME_MAP = {
    # ── Classic Blue on Dark ──
    "blue-dark": {
        "title": "bold dodger_blue2",
        "label": "cornflower_blue",
        "meta": "grey62",
        "ok": "medium_spring_green",
        "warning": "gold1",
        "danger": "indian_red1",
    },
    # ── Classic Blue on Light ──
    "blue-light": {
        "title": "bold blue",
        "label": "dark_blue",
        "meta": "grey35",
        "ok": "dark_green",
        "warning": "dark_orange",
        "danger": "red3",
    },
    # ── Royal Sky Blue on Dark ──
    "sky-dark": {
        "title": "bold royal_blue1",
        "label": "sky_blue1",
        "meta": "grey58",
        "ok": "spring_green2",
        "warning": "orange1",
        "danger": "light_coral",
    },
    # ── Salmon Saffron on Dark ──
    "salmon-dark": {
        "title": "bold light_salmon3",
        "label": "sandy_brown",
        "meta": "grey46",
        "ok": "dark_sea_green2",
        "warning": "gold3",
        "danger": "indian_red",
    },
    # ── Turquoise Aquamarine on Dark ──
    "turquoise-dark": {
        "title": "bold turquoise2",
        "label": "medium_aquamarine",
        "meta": "grey53",
        "ok": "aquamarine1",
        "warning": "khaki1",
        "danger": "hot_pink",
    },
    # ── Rose Pink on Light ──
    "pink-light": {
        "title": "bold deep_pink3",
        "label": "hot_pink3",
        "meta": "grey37",
        "ok": "dark_cyan",
        "warning": "dark_goldenrod",
        "danger": "red3",
    },
    # ── Deep Purple on Dark ──
    "violet-dark": {
        "title": "bold medium_purple2",
        "label": "medium_purple1",
        "meta": "grey54",
        "ok": "spring_green3",
        "warning": "orange1",
        "danger": "plum1",
    },
    # ── Warm Saffron Orange on Dark ──
    "amber-dark": {
        "title": "bold dark_orange",
        "label": "gold1",
        "meta": "grey54",
        "ok": "green_yellow",
        "warning": "gold3",
        "danger": "red1",
    },
    # ── Mint Teal on Dark ──
    "mint-dark": {
        "title": "bold dark_cyan",
        "label": "light_sea_green",
        "meta": "grey54",
        "ok": "medium_spring_green",
        "warning": "khaki1",
        "danger": "indian_red1",
    },
    # ── Monochrome ──
    "monochrome": {
        "title": "bold white",
        "label": "white",
        "meta": "grey46",
        "ok": "white",
        "warning": "grey74",
        "danger": "bold reverse",
    },
    # ── Red-Green Blind Friendly ──
    "blind-deuteranopia": {
        "title": "bold dodger_blue1",
        "label": "cornflower_blue",
        "meta": "grey62",
        "ok": "dodger_blue1",
        "warning": "gold1",
        "danger": "dark_orange",
    },
    # ── Blue-Yellow Blind Friendly ──
    "blind-tritanopia": {
        "title": "bold red1",
        "label": "light_coral",
        "meta": "grey62",
        "ok": "chartreuse3",
        "warning": "pale_green3",
        "danger": "bold red1",
    },
}




def _handle_key(ch: str, idx: int, n: int) -> tuple[int, bool, bool, int | None, bool, bool, bool]:
    """Map a keypress to a TUI action.

    Returns:
        (new_idx, should_quit, should_refresh, toggle_provider_num, lang_toggle, metric_toggle, days_toggle)
    """
    if ch in ('q', 'Q', '\x03', '\x04'):       # q  Ctrl-C  Ctrl-D
        return idx, True, False, None, False, False, False
    if ch in (']', 'n', '\t', '\x1b[C'):        # ]  n  Tab  →
        return (idx + 1) % n, False, False, None, False, False, False
    if ch in ('[', 'p', '\x1b[D'):              # [  p  ←
        return (idx - 1) % n, False, False, None, False, False, False
    if ch in ('r', 'R'):                        # r → refresh data
        return idx, False, True, None, False, False, False
    if ch in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):              # 1-6 → toggle provider panel
        return idx, False, False, int(ch) - 1, False, False, False
    if ch in ('l', 'L'):                        # l → toggle language zh/en
        return idx, False, False, None, True, False, False
    if ch in ('m', 'M'):                        # m → toggle OpenRouter metric
        return idx, False, False, None, False, True, False
    if ch in ('d', 'D'):                        # d → toggle days window
        return idx, False, False, None, False, False, True
    return idx, False, False, None, False, False, False


def _format_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:.0f}"


def _model_short_name(model: str) -> str:
    if "/" in model:
        return model.rsplit("/", 1)[-1]
    return model


# --- OpenRouter metric helpers ---
OR_METRIC_SPEND = "spend"
OR_METRIC_REQUESTS = "requests"
OR_METRIC_TOKENS = "tokens"
VALID_OR_METRICS = (OR_METRIC_SPEND, OR_METRIC_REQUESTS, OR_METRIC_TOKENS)

# --- OpenRouter days window helpers ---
DAYS_WINDOWS = (7, 14, 30, 60, 90)


def _parse_days_window(value) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 30
    return value if value in DAYS_WINDOWS else 30


def _next_days_window(days_window: int) -> int:
    try:
        idx = DAYS_WINDOWS.index(days_window)
    except ValueError:
        return 30
    return DAYS_WINDOWS[(idx + 1) % len(DAYS_WINDOWS)]


def _parse_or_metric(value: str | None) -> str:
    if value in VALID_OR_METRICS:
        return value
    return OR_METRIC_REQUESTS


def _next_or_metric(metric: str) -> str:
    order = (OR_METRIC_SPEND, OR_METRIC_REQUESTS, OR_METRIC_TOKENS)
    try:
        idx = order.index(metric)
    except ValueError:
        return OR_METRIC_REQUESTS
    return order[(idx + 1) % len(order)]


def _metric_label(metric: str, lang_zh: bool) -> str:
    labels = {
        OR_METRIC_SPEND: ("支出", "Spend"),
        OR_METRIC_REQUESTS: ("请求", "Requests"),
        OR_METRIC_TOKENS: ("Tokens", "Tokens"),
    }
    return labels.get(metric, labels[OR_METRIC_SPEND])[0 if lang_zh else 1]


def _metric_value_model(mu, metric: str) -> float:
    if metric == OR_METRIC_REQUESTS:
        return mu.requests
    if metric == OR_METRIC_TOKENS:
        return mu.prompt_tokens + mu.completion_tokens + mu.reasoning_tokens
    return mu.spend


def _metric_value_day(day, metric: str) -> float:
    if metric == OR_METRIC_SPEND:
        return day.total
    return sum(_metric_value_model(m, metric) for m in day.models)


def _format_metric_value(value: float, metric: str) -> str:
    if metric == OR_METRIC_SPEND:
        return f"${value:.2f}"
    if metric == OR_METRIC_TOKENS:
        return _format_tokens(value)
    return f"{value:,.0f}"


def _render_activity_totals(totals, lang_zh: bool, theme: dict) -> Text:
    text = Text()
    title = "活动" if lang_zh else "Activity"
    text.append(f"  {title}\n", style=theme.get("label", "cornflower_blue"))
    parts = []
    if totals.requests:
        req_label = "请求" if lang_zh else "Req"
        parts.append(f"{req_label}: {totals.requests:,.0f}")
    if totals.prompt_tokens or totals.completion_tokens:
        in_label = "输入" if lang_zh else "In"
        out_label = "输出" if lang_zh else "Out"
        tok = f"{in_label}: {_format_tokens(totals.prompt_tokens)} / {out_label}: {_format_tokens(totals.completion_tokens)}"
        if totals.reasoning_tokens:
            reason_label = "推理" if lang_zh else "reason"
            tok += f" (+ {_format_tokens(totals.reasoning_tokens)} {reason_label})"
        parts.append(tok)
    if totals.spend:
        spend_label = "支出" if lang_zh else "Spend"
        parts.append(f"{spend_label}: ${totals.spend:.2f}")
    text.append("    " + " | ".join(parts), style=theme.get("meta", "grey62"))
    return text


def _render_daily_chart(daily_activity, lang_zh: bool, theme: dict, metric: str = OR_METRIC_REQUESTS, days_window: int = 30, color_map: dict[str, str] | None = None) -> Text:
    if not daily_activity:
        return Text()
    metric = _parse_or_metric(metric)
    days_window = _parse_days_window(days_window)

    from datetime import datetime, timedelta

    # Build a contiguous date range of `days_window` days ending at the latest activity date.
    sorted_days = sorted(daily_activity, key=lambda d: d.date)
    latest_date = datetime.strptime(sorted_days[-1].date[:10], "%Y-%m-%d")
    start_date = latest_date - timedelta(days=days_window - 1)

    day_lookup: dict[str, DailyUsage] = {}
    for d in sorted_days:
        key = d.date[:10] if len(d.date) >= 10 else d.date
        if key in day_lookup:
            existing = day_lookup[key]
            merged_models = existing.models + d.models
            day_lookup[key] = DailyUsage(date=key, models=merged_models, total=existing.total + d.total)
        else:
            day_lookup[key] = DailyUsage(date=key, models=list(d.models), total=d.total)

    days: list[DailyUsage] = []
    for i in range(days_window):
        date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        days.append(day_lookup.get(date, DailyUsage(date=date, models=[], total=0.0)))

    # Chart dimensions inspired by tokentop: clamp column width to [1, 4] and
    # cap the total rendered width so the chart fits a typical terminal panel.
    height = 9
    top_models_limit = 6
    max_chart_width = 70
    col_width = 1
    if len(days) > 0:
        col_width = max_chart_width // len(days)
        if col_width > 4:
            col_width = 4
        if col_width < 1:
            col_width = 1
    # If the full window would exceed the max width, trim to the most recent days.
    if len(days) * col_width > max_chart_width:
        keep = max_chart_width // col_width
        days = days[-keep:]

    max_total = max(_metric_value_day(d, metric) for d in days) or 1.0

    # Find top models across all days for consistent coloring
    model_totals_all: dict[str, float] = {}
    for day in days:
        for model in day.models:
            model_totals_all[model.model] = model_totals_all.get(model.model, 0.0) + _metric_value_model(model, metric)
    top_models = _top_n_models(model_totals_all, top_models_limit)
    top_model_set = set(top_models)
    # Build a color palette aligned to `top_models`, plus a trailing neutral color
    # for the "others" bucket. When a shared color_map is supplied, colors are
    # keyed by model name so this chart agrees with the Top Models chart.
    _colors = _model_colors(theme)
    if color_map is not None:
        palette = [color_map.get(name, _colors[i % len(_colors)]) for i, name in enumerate(top_models)]
    else:
        palette = [_colors[i % len(_colors)] for i in range(len(top_models))]
    palette.append(theme.get("meta", "grey62"))  # "others" bucket → neutral
    others_color_idx = len(top_models)  # index of the "others" color in `palette`

    # Pre-compute each column as color indices (bottom -> top)
    columns: list[list[int | None]] = []
    for day in days:
        value_by_model: dict[str, float] = {}
        others_value = 0.0
        for model in day.models:
            v = _metric_value_model(model, metric)
            if model.model in top_model_set:
                value_by_model[model.model] = value_by_model.get(model.model, 0.0) + v
            else:
                others_value += v

        segments: list[tuple[int, float]] = []
        for i, name in enumerate(top_models):
            if v := value_by_model.get(name, 0.0):
                segments.append((i, v))
        if others_value > 0:
            segments.append((others_color_idx, others_value))

        day_total = sum(v for _, v in segments)
        column: list[int | None] = [None] * height
        if day_total > 0 and max_total > 0:
            total_cells = max(1, min(height, int(round(day_total / max_total * height))))
            exacts = [seg[1] / day_total * total_cells for seg in segments]
            counts = [int(x) for x in exacts]
            remainders = [exacts[i] - counts[i] for i in range(len(segments))]
            allocated = sum(counts)
            while allocated < total_cells:
                best = max(range(len(remainders)), key=lambda i: remainders[i])
                counts[best] += 1
                remainders[best] = -1
                allocated += 1

            cell_idx = 0
            for seg_idx, (cidx, _) in enumerate(segments):
                for _ in range(counts[seg_idx]):
                    if cell_idx < height:
                        column[cell_idx] = cidx
                        cell_idx += 1
        columns.append(column)

    text = Text()
    title_label = _metric_label(metric, lang_zh)
    title = f"每日{title_label}" if lang_zh else f"Daily {title_label.title()}"
    text.append(f"  {title}\n\n", style=theme.get("label", "cornflower_blue"))

    # Y-axis gutter
    y_labels = [max_total, max_total / 2, max_total / float(height)]
    y_label_strs = [_format_metric_value(v, metric) for v in y_labels]
    gutter_width = max(len(s) for s in y_label_strs) + 1
    gutter_fmt = f"{{:>{gutter_width}s}}"
    empty_gutter = " " * gutter_width
    # Indent the whole chart body to align with the title above
    chart_indent = "  "

    filled_glyph = "▐" + "█" * (col_width - 1)
    empty_glyph = " " * col_width

    # Render rows top -> bottom
    for row in range(height - 1, -1, -1):
        text.append(chart_indent, style=theme.get("meta", "grey62"))
        if row == height - 1:
            text.append(gutter_fmt.format(y_label_strs[0]), style=theme.get("meta", "grey62"))
        elif row == height // 2:
            text.append(gutter_fmt.format(y_label_strs[1]), style=theme.get("meta", "grey62"))
        elif row == 0:
            text.append(gutter_fmt.format(y_label_strs[2]), style=theme.get("meta", "grey62"))
        else:
            text.append(empty_gutter, style=theme.get("meta", "grey62"))

        text.append("│", style=theme.get("meta", "grey62"))
        for col in columns:
            cidx = col[row]
            if cidx is not None:
                color = palette[cidx]
                text.append(filled_glyph, style=color)
            else:
                text.append(empty_glyph)
        text.append("\n")

    # X-axis line
    text.append(chart_indent + empty_gutter + "└" + "─" * (col_width * len(days)) + "\n", style=theme.get("meta", "grey62"))

    # Date labels: distribute evenly based on how many column slots a label
    # occupies. A date label is 5 chars; we want at least 2 chars of visual gap.
    if len(days) > 0:
        date_line = Text(chart_indent + empty_gutter + " ")
        label_len = len(short_date(days[0].date))
        # Number of column slots needed per label (including desired gap)
        slot_gap = max(1, (label_len + 2 + col_width - 1) // col_width)

        label_positions = set(range(0, len(days), slot_gap))
        # Always include the last day if not already present and it fits.
        if len(days) > 1 and (len(days) - 1) % slot_gap != 0:
            label_positions.add(len(days) - 1)
        label_positions = sorted(label_positions)

        max_line_chars = len(days) * col_width
        skip = 0
        for i, day in enumerate(days):
            if skip > 0:
                skip -= 1
                continue
            if i in label_positions:
                lbl = short_date(day.date)
                date_line.append(lbl, style=theme.get("meta", "grey62"))
                consumed_cols = max(1, (len(lbl) + col_width - 1) // col_width)
                # Pad to the column boundary, but never beyond the chart width
                current_pos = i * col_width + len(lbl)
                target_pos = min(i * col_width + consumed_cols * col_width, max_line_chars)
                padding = target_pos - current_pos
                if padding > 0:
                    date_line.append(" " * padding)
                skip = consumed_cols - 1
            else:
                date_line.append(" " * col_width)
        text.append(date_line)
        text.append("\n")

    # Legend
    if top_models:
        text.append("\n")
        text.append("     ", style=theme.get("meta", "grey62"))
        for i, model in enumerate(top_models[:8]):
            name = truncate(_model_short_name(model), 14)
            color = palette[i]
            text.append("█", style=color)
            text.append(f" {name}  ", style=theme.get("meta", "grey62"))
        text.append("\n")

    return text


def _model_colors(theme: dict) -> list[str]:
    return [
        theme.get("ok", "medium_spring_green"),
        theme.get("warning", "gold1"),
        theme.get("danger", "indian_red1"),
        "dodger_blue1",
        "medium_purple1",
        "dark_orange",
        "turquoise2",
        "hot_pink",
        "spring_green2",
        "gold3",
    ]


def _build_model_color_map(model_names: list[str], theme: dict) -> dict[str, str]:
    """Map each model name to a stable color so every panel colors it the same.

    ``model_names`` is expected in canonical (metric-descending) order, so the
    top-ranked model gets the first color. Colors cycle when there are more
    models than palette entries.
    """
    colors = _model_colors(theme)
    return {name: colors[i % len(colors)] for i, name in enumerate(model_names)}


def _build_openrouter_color_map(rows, metric: str, theme: dict) -> dict[str, str] | None:
    """Build one shared model→color map for an OpenRouter provider's rows.

    The daily chart and the Top Models chart live in separate ``ProviderUsage``
    rows but must agree on colors. We rank models by the currently displayed
    metric (preferring the aggregate ``top_models`` row, else ``daily_activity``)
    so the same model gets the same color in both. Returns ``None`` when the
    rows carry no model breakdown (e.g. non-OpenRouter providers).
    """
    metric = _parse_or_metric(metric)
    totals: dict[str, float] = {}
    top_row = next((r for r in rows if r.top_models), None)
    if top_row and top_row.top_models:
        for m in top_row.top_models:
            totals[m.model] = totals.get(m.model, 0.0) + _metric_value_model(m, metric)
    else:
        for row in rows:
            if row.daily_activity:
                for day in row.daily_activity:
                    for m in day.models:
                        totals[m.model] = totals.get(m.model, 0.0) + _metric_value_model(m, metric)
    if not totals:
        return None
    ordered = [name for name, _ in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))]
    return _build_model_color_map(ordered, theme)


def _top_n_models(model_totals: dict[str, float], n: int) -> list[str]:
    items = sorted(model_totals.items(), key=lambda x: (-x[1], x[0]))
    return [m for m, _ in items[:n]]


def short_date(date: str) -> str:
    if len(date) >= 10:
        return date[5:10]
    return date


def truncate(s: str, max_len: int) -> str:
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s



def _window_top_models(daily_activity, days_window: int, metric: str) -> list[ModelUsage]:
    """Rank models within the current [d] window, so Top Models tracks the Daily chart.

    Mirrors the daily chart's window (a contiguous range of ``days_window`` days
    ending at the latest activity date), aggregates each model's usage across those
    days, and returns them ranked by ``metric`` descending. Returns an empty list
    when there is no dated activity to window over.
    """
    if not daily_activity:
        return []
    from datetime import datetime, timedelta

    metric = _parse_or_metric(metric)
    days_window = _parse_days_window(days_window)
    sorted_days = sorted(daily_activity, key=lambda d: d.date)
    latest_date = datetime.strptime(sorted_days[-1].date[:10], "%Y-%m-%d")
    start_date = latest_date - timedelta(days=days_window - 1)

    agg: dict[str, ModelUsage] = {}
    for day in sorted_days:
        key = day.date[:10] if len(day.date) >= 10 else day.date
        try:
            day_date = datetime.strptime(key, "%Y-%m-%d")
        except ValueError:
            continue
        if day_date < start_date or day_date > latest_date:
            continue
        for m in day.models:
            existing = agg.get(m.model)
            if existing is None:
                agg[m.model] = ModelUsage(
                    model=m.model,
                    spend=m.spend,
                    requests=m.requests,
                    prompt_tokens=m.prompt_tokens,
                    completion_tokens=m.completion_tokens,
                    reasoning_tokens=m.reasoning_tokens,
                )
            else:
                existing.spend += m.spend
                existing.requests += m.requests
                existing.prompt_tokens += m.prompt_tokens
                existing.completion_tokens += m.completion_tokens
                existing.reasoning_tokens += m.reasoning_tokens
    return sorted(agg.values(), key=lambda m: (-_metric_value_model(m, metric), m.model))


def _render_top_models(top_models, lang_zh: bool, theme: dict, metric: str = OR_METRIC_REQUESTS, chart_width: int = 20, color_map: dict[str, str] | None = None) -> Text:
    if not top_models:
        return Text()
    metric = _parse_or_metric(metric)
    max_val = max(_metric_value_model(m, metric) for m in top_models) or 1.0
    text = Text()
    title = "Top 模型" if lang_zh else "Top Models"
    text.append(f"  {title}\n", style=theme.get("label", "cornflower_blue"))
    colors = [
        theme.get("ok", "medium_spring_green"),
        theme.get("warning", "gold1"),
        theme.get("danger", "indian_red1"),
        "dodger_blue1",
        "medium_purple1",
        "dark_orange",
        "turquoise2",
    ]
    for i, m in enumerate(top_models[:7]):
        val = _metric_value_model(m, metric)
        bar_len = int(val / max_val * chart_width) if max_val > 0 else 0
        name = _model_short_name(m.model)
        if len(name) > 22:
            name = name[:19] + "..."
        color = color_map.get(m.model, colors[i % len(colors)]) if color_map else colors[i % len(colors)]
        text.append(f"    {name:22} ", style=theme.get("meta", "grey62"))
        text.append(f"{_format_metric_value(val, metric):>8}  ", style=theme.get("meta", "grey62"))
        text.append("█" * bar_len, style=color)
        text.append("░" * (chart_width - bar_len) + "\n", style="grey50")
    return text



def _format_aggregated_results(
    results: dict[str, list[ProviderUsage]],
    errors: dict[str, str],
    order: list[str] | None = None,
    theme_name: str = "blue-dark",
    lang_zh: bool = IS_ZH,
    enabled_providers: set | None = None,
    or_metric: str = OR_METRIC_REQUESTS,
    days_window: int = 30,
) -> Text:
    _L = L_ZH if lang_zh else L_EN
    result = Text()
    if order is None:
        order = ["anthropic", "openai", "openrouter", "kimi"]

    theme = THEME_MAP.get(theme_name)
    if not theme:
        theme = THEME_MAP["blue-dark"]

    # First pass: pre-render all bodies and find global_max_width
    provider_bodies = {}
    error_msgs = {}
    global_max_width = 0

    for p in order:
        p_items = results.get(p)
        if not p_items:
            continue

        visual_widths = [_get_visual_width(_get_localized_label(r.label, lang_zh)) for r in p_items]
        # Include metadata labels if applicable to ensure correct alignment padding
        has_countdown = any(r.countdown for r in p_items)
        has_reset = any(r.reset_at for r in p_items)
        if has_countdown:
            visual_widths.append(_get_visual_width(_L['countdown']))
        if has_reset:
            visual_widths.append(_get_visual_width(_L['reset']))

        max_visual_width = max(visual_widths) if visual_widths else 0
        max_visual_width = max(max_visual_width, 6)
        bar_width = 20

        body_text = Text()
        # Shared model→color map so the daily chart and Top Models agree on colors.
        model_color_map = _build_openrouter_color_map(p_items, or_metric, theme)
        # Top Models tracks the [d] window: recompute the ranking from the dated
        # daily activity so switching the window updates it (consistent with the chart).
        _daily_row = next((r for r in p_items if r.daily_activity), None)
        for i, row in enumerate(p_items):
            if i > 0:
                body_text.append("\n")

            has_structured = row.activity_totals or row.daily_activity or row.top_models

            if has_structured:
                # Structured rows render only their visualizations, no generic label line
                if row.activity_totals:
                    if i > 0:
                        body_text.append("\n")
                    body_text.append(_render_activity_totals(row.activity_totals, lang_zh, theme))
                if row.daily_activity:
                    if i > 0 or row.activity_totals:
                        body_text.append("\n")
                    body_text.append(_render_daily_chart(row.daily_activity, lang_zh, theme, metric=or_metric, days_window=days_window, color_map=model_color_map))
                if row.top_models:
                    if i > 0 or row.activity_totals or row.daily_activity:
                        body_text.append("\n")
                    _windowed = _window_top_models(_daily_row.daily_activity, days_window, or_metric) if _daily_row else []
                    body_text.append(_render_top_models(_windowed or row.top_models, lang_zh, theme, metric=or_metric, chart_width=20, color_map=model_color_map))
                continue

            loc_label = _get_localized_label(row.label, lang_zh)
            label_v_width = _get_visual_width(loc_label)
            padding = " " * (max_visual_width - label_v_width)

            body_text.append(f"  {loc_label}{padding}  ", style=theme["label"])

            if row.limit is not None and row.limit > 0:
                used_ratio = row.used / row.limit
                remaining_percent = max(0.0, 100.0 - (used_ratio * 100.0))
                color = theme["danger"] if used_ratio > 0.9 else theme["warning"] if used_ratio > 0.7 else theme["ok"]
                filled = min(bar_width, int(used_ratio * bar_width))

                body_text.append("█" * filled, style=color)
                body_text.append("·" * (bar_width - filled), style="grey50")

                if row.unit == "%":
                    body_text.append(f"  {used_ratio * 100:.0f}%   {remaining_percent:.0f}% {_L['remaining']}", style="bold")
                elif row.unit == "$":
                    body_text.append(f"  ${row.used:.2f} / ${row.limit:.2f} ({remaining_percent:.0f}% {_L['remaining']})", style="bold")
                else:
                    body_text.append(f"  {row.used:,.0f} / {row.limit:,.0f} {row.unit} ({remaining_percent:.0f}% {_L['remaining']})", style="bold")
            else:
                if row.unit == "$":
                    body_text.append(f"  ${row.used:.2f}", style="bold")
                elif row.unit == "text":
                    if row.text_value:
                        loc_val = _get_localized_text_value(row.text_value, lang_zh)
                        body_text.append(f"  {loc_val}", style="bold")
                else:
                    body_text.append(f"  {row.used:,.0f} {row.unit}", style="bold")

            if row.countdown:
                body_text.append("\n")
                meta_label = _L['countdown']
                meta_padding = " " * (max_visual_width - _get_visual_width(meta_label))
                body_text.append(f"  {meta_label}{meta_padding}  ", style=theme["label"])
                body_text.append(row.countdown, style="bold")
            if row.reset_at:
                body_text.append("\n")
                meta_label = _L['reset']
                meta_padding = " " * (max_visual_width - _get_visual_width(meta_label))
                body_text.append(f"  {meta_label}{meta_padding}  ", style=theme["label"])
                body_text.append(row.reset_at, style="bold")

        provider_bodies[p] = body_text
        lines = body_text.plain.split("\n")
        max_line_width = max((_get_visual_width(line) for line in lines), default=0)
        if max_line_width > global_max_width:
            global_max_width = max_line_width

    # 2. Process errors and unconfigured visible providers
    for p in order:
        if p in errors:
            err = errors[p]
            if err == "Not configured" and lang_zh:
                translated_err = "未配置"
            else:
                translated_err = err
            err_msg = f"  ⚠ {translated_err}"
            error_msgs[p] = err_msg
            err_width = _get_visual_width(err_msg)
            if err_width > global_max_width:
                global_max_width = err_width
        elif p not in results:
            if enabled_providers is not None and p not in enabled_providers:
                continue
            err_msg = "  ⚠ 未配置" if lang_zh else "  ⚠ Not configured"
            error_msgs[p] = err_msg
            err_width = _get_visual_width(err_msg)
            if err_width > global_max_width:
                global_max_width = err_width

    max(50, global_max_width + 4)

    # Second pass: construct final result with simple divider titles
    for p in order:
        body_text = provider_bodies.get(p)
        err_msg = error_msgs.get(p)

        # Dynamic title for codex: use plan_type from API response
        if p == "codex":
            p_items = results.get(p, [])
            plan_row = next((r for r in p_items if r.label == "Plan"), None)
            plan_title = plan_row.text_value if plan_row and plan_row.text_value else "ChatGPT Plus"
        else:
            plan_title = None

        _PROVIDER_TITLES = {
            "kimi": "Kimi",
            "codex": plan_title or "ChatGPT Plus",
            "openai": "OpenAI API",
            "anthropic": "Anthropic",
            "openrouter": "OpenRouter",
            "claude": "Claude",
        }
        title_str = _PROVIDER_TITLES.get(p, p.capitalize())
        divider_line = f"───────── {title_str} ─────────"

        if body_text:
            result.append(f"{divider_line}\n", style=theme["title"])
            result.append("\n")  # Empty line between divider and text
            result.append(body_text)

        if err_msg:
            if not body_text:
                result.append(f"{divider_line}\n", style=theme["danger"])
                result.append("\n")  # Empty line between divider and error
            else:
                result.append("\n\n")  # Empty line between body and error
            result.append(f"{err_msg}", style=theme["danger"])

        result.append("\n\n")  # Empty line below provider section

    return result


def _fit_scroll_body(body: Text, budget: int, scroll_offset: int, lang_zh: bool) -> tuple[Text, int]:
    """Clamp a body ``Text`` to ``budget`` lines with an in-panel scroll offset.

    Keeps the interactive panel within the terminal height so the control hint
    bar is never cropped and Rich never has to scroll the screen (which would
    duplicate the header). When the body overflows, returns the visible slice
    plus a scroll-indicator line; otherwise returns the body unchanged. The
    second return value is the clamped offset the caller should store back.
    """
    if budget < 1:
        budget = 1
    lines = body.split("\n")
    total = len(lines)
    if total <= budget:
        return body, 0
    view_rows = max(1, budget - 1)  # reserve one line for the scroll indicator
    max_off = max(0, total - view_rows)
    off = max(0, min(scroll_offset, max_off))
    visible = list(lines[off:off + view_rows])
    up = "▲" if off > 0 else "·"
    down = "▼" if off + view_rows < total else "·"
    label = "滚动" if lang_zh else "scroll"
    indicator = Text(
        f"  {up} {off + 1}–{min(off + view_rows, total)}/{total} {down}  [↑/↓ PgUp/PgDn {label}]",
        style="dim",
    )
    return Text("\n").join([*visible, indicator]), off


async def _interactive_mode(config: "AppConfig", initial_theme: str, config_path: str | None = None) -> None:
    """Live Rich TUI with keyboard theme cycling and provider panel toggling.

    Keys:
        ←/→ or [ / ]  — cycle theme
        1 / 2 / 3 / 4  — toggle provider panels
        r              — refresh data
        q / Ctrl-C     — quit
    """
    import termios
    import tty

    themes = list(THEME_MAP.keys())
    try:
        idx = themes.index(initial_theme)
    except ValueError:
        idx = 0

    results: dict[str, list[ProviderUsage]] = {}
    errors: dict[str, str] = {}

    # Determine initial visible providers and language
    if config.visible_providers is not None:
        visible_providers: set = {p for p in config.visible_providers if p in config.provider_order}
    else:
        visible_providers: set = set(config.provider_order)

    if config.language == "zh":
        lang_zh: bool = True
    elif config.language == "en":
        lang_zh: bool = False
    else:
        lang_zh: bool = IS_ZH

    or_metric: str = _parse_or_metric(config.or_metric)
    days_window: int = _parse_days_window(config.days_window)
    current_view = "usage"

    saved_notice: list = [None]   # holds the saved theme name briefly, then None
    scroll: list = [0]            # in-panel vertical scroll offset (lines from top)
    settings_cursor: list = [0]       # cursor position in settings view


    def _build_panel() -> Panel:
        visible_order = [p for p in config.provider_order if p in visible_providers]
        _L = L_ZH if lang_zh else L_EN
        if current_view == "help":
            body = _render_interactive_help(lang_zh, or_metric=or_metric, days_window=days_window, provider_count=len(config.provider_order))
        elif current_view == "config":
            body = _render_config_guide(config, lang_zh=lang_zh, config_path=config_path)
        elif current_view == "settings":
            body = _render_setting_view(config, visible_providers, settings_cursor=settings_cursor[0], lang_zh=lang_zh)
        else:
            body = _format_aggregated_results(results, errors, visible_order, themes[idx], lang_zh, enabled_providers=set(config.enabled_providers), or_metric=or_metric, days_window=days_window)

        top_bar = Text()
        # Provider toggles
        for i, p in enumerate(config.provider_order, 1):
            short = _SHORT.get(p, p[:4].title())
            if p in visible_providers:
                top_bar.append("● ", style="bold")
                top_bar.append(f"[{i}]{short}  ", style="bold")
            else:
                top_bar.append("○ ", style="dim")
                top_bar.append(f"[{i}]{short}  ", style="dim italic")
        # Theme name
        top_bar.append("│  ", style="dim")
        top_bar.append("主题: " if lang_zh else "theme: ", style="dim")
        top_bar.append(themes[idx], style="bold")
        top_bar.justify = "center"

        hint = Text()
        # Keybindings grouped logically: navigation / view / data / persistence
        bindings = [
            ("[q]", "退出" if lang_zh else "quit"),
            ("[r]", "刷新" if lang_zh else "refresh"),
            ("[h/?]", "帮助" if lang_zh else "help"),
            ("[c]", "配置" if lang_zh else "config"),
            ("[s]", "设置" if lang_zh else "settings"),
            ("[←/→]", "主题" if lang_zh else "theme"),
            (f"[1-{len(config.provider_order)}]", "面板" if lang_zh else "panels"),
            ("[↑↓]", "滚动" if lang_zh else "scroll"),
            ("[l]", "英" if lang_zh else "ZH"),
            ("[m]", _metric_label(or_metric, lang_zh)),
            ("[d]", f"{days_window}d"),
            ("[⏎ ]", "保存" if lang_zh else "save"),
        ]
        for i, (key, label) in enumerate(bindings):
            if i > 0:
                hint.append("  ", style="dim")
            hint.append(key, style="bold")
            hint.append(f" {label}", style="dim")
        if saved_notice[0]:
            hint.append(f"  ✓ {'已保存' if lang_zh else 'Saved'}: {saved_notice[0]}", style="bold green")
        hint.justify = "center"

        # Keep top_bar and hint to a single line each so the fit math below is exact.
        top_bar.no_wrap = True
        top_bar.overflow = "ellipsis"
        hint.no_wrap = True
        hint.overflow = "ellipsis"

        # Fit the body to the terminal so the hint bar is never cropped and Rich
        # never scrolls the screen (which duplicates the header). Overhead:
        # border(2) + padding(2) + top_bar(1) + gap(1) + hint(1) = 7 lines.
        body_budget = max(3, console.size.height - 7)
        if isinstance(body, Text):
            body, scroll[0] = _fit_scroll_body(body, body_budget, scroll[0], lang_zh)

        panel_content = Group(
            top_bar,
            Text(""),
            body,
            hint
        )

        return Panel(panel_content, title=f"[bold]{_L['title']}[/bold]", subtitle=None,
                     expand=True, padding=(1, 2, 1, 2))

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def _read_char() -> str:
        # Prevent input buffering split by using os.read in raw terminal; fall back to stdin.read under tests
        is_mock = hasattr(sys.stdin.read, "mock") or hasattr(sys.stdin.read, "_mock_self") or "mock" in type(sys.stdin.read).__name__.lower()
        if not is_mock and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():  # pragma: no cover
            import os
            try:
                b = os.read(fd, 1)
                if b:
                    return b.decode('utf-8', errors='ignore')
            except Exception:
                pass
        return sys.stdin.read(1)

    try:
        tty.setcbreak(fd)
        results, errors = await dispatch_all(config)
        console = Console()
        with Live(_build_panel(), console=console, auto_refresh=False, vertical_overflow="crop") as live:
            running = True
            while running:
                rlist, _, _ = _select_module.select([sys.stdin], [], [], 0.15)
                if rlist:
                    ch = _read_char()
                    if not ch:  # pragma: no cover
                        continue

                    if ch == '\x1b':
                        r2, _, _ = _select_module.select([sys.stdin], [], [], 0.05)
                        if r2:
                            ch2 = _read_char()
                            if ch2 == '[':
                                r3, _, _ = _select_module.select([sys.stdin], [], [], 0.05)
                                if r3:
                                    ch3 = _read_char()
                                    if ch3.isdigit():
                                        # CSI sequences like PgUp (\x1b[5~) / PgDn (\x1b[6~)
                                        r4, _, _ = _select_module.select([sys.stdin], [], [], 0.05)
                                        tilde = _read_char() if r4 else ""
                                        ch = f'\x1b[{ch3}{tilde}'
                                    else:
                                        ch = f'\x1b[{ch3}'

                    if saved_notice[0]:     # clear notice on any new keypress
                        saved_notice[0] = None
                    if ch in ('h', 'H', '?'):
                        current_view = "usage" if current_view == "help" else "help"
                        scroll[0] = 0
                        live.update(_build_panel(), refresh=True)
                        continue
                    if ch in ('c', 'C'):
                        current_view = "usage" if current_view == "config" else "config"
                        scroll[0] = 0
                        live.update(_build_panel(), refresh=True)
                        continue
                    if ch in ('s', 'S'):
                        current_view = "usage" if current_view == "settings" else "settings"
                        scroll[0] = 0
                        live.update(_build_panel(), refresh=True)
                        continue
                    if ch in ('\r', '\n'):  # Enter → save settings to config file
                        save_theme(
                            themes[idx],
                            language="zh" if lang_zh else "en",
                            visible_providers=list(visible_providers),
                            or_metric=or_metric,
                            days_window=days_window
                        )
                        saved_notice[0] = themes[idx]
                        live.update(_build_panel(), refresh=True)
                        # Flush any consecutive \r or \n (like \r\n from terminal)
                        while True:
                            r_extra, _, _ = _select_module.select([sys.stdin], [], [], 0.0)
                            if r_extra:  # pragma: no cover
                                extra_ch = _read_char()
                                if extra_ch in ('\r', '\n'):  # pragma: no cover
                                    continue
                            break
                        continue
                    if ch == '\x1b[A':          # ↑ → scroll up or move cursor up in settings
                        if current_view == "settings":
                            settings_cursor[0] = max(0, settings_cursor[0] - 1)
                            live.update(_build_panel(), refresh=True)
                        else:
                            scroll[0] = max(0, scroll[0] - 3)
                            live.update(_build_panel(), refresh=True)
                        continue
                    if ch == '\x1b[B':          # ↓ → scroll down or move cursor down in settings
                        if current_view == "settings":
                            providers = config.provider_order
                            settings_cursor[0] = min(len(providers) - 1, settings_cursor[0] + 1)
                            live.update(_build_panel(), refresh=True)
                        else:
                            scroll[0] += 3
                            live.update(_build_panel(), refresh=True)
                        continue
                    if ch in ('\x1b[C', ']'):   # → / ] → move item right/down in settings
                        if current_view == "settings":
                            providers = config.provider_order
                            cur = settings_cursor[0]
                            if cur < len(providers) - 1:
                                providers[cur], providers[cur+1] = providers[cur+1], providers[cur]
                                settings_cursor[0] = cur + 1
                            live.update(_build_panel(), refresh=True)
                            continue
                        # In usage view, fall through to _handle_key for theme cycling
                    if ch in ('\x1b[D', '['):   # ← / [ → move item left/up in settings
                        if current_view == "settings":
                            providers = config.provider_order
                            cur = settings_cursor[0]
                            if cur > 0:
                                providers[cur], providers[cur-1] = providers[cur-1], providers[cur]
                                settings_cursor[0] = cur - 1
                            live.update(_build_panel(), refresh=True)
                            continue
                        # In usage view, fall through to _handle_key for theme cycling
                    if ch in ('\x1b[5~', '\x1b[6~'):  # PgUp / PgDn → page scroll
                        page = max(1, console.size.height - 8)
                        scroll[0] = max(0, scroll[0] + (page if ch == '\x1b[6~' else -page))
                        live.update(_build_panel(), refresh=True)
                        continue
                    idx, quit_flag, refresh_flag, toggle_num, lang_toggle, metric_toggle, days_toggle = _handle_key(ch, idx, len(themes))
                    if quit_flag:
                        running = False
                    elif refresh_flag:
                        results, errors = await dispatch_all(config)
                        scroll[0] = 0
                    elif toggle_num is not None:
                        providers = list(config.provider_order)
                        if toggle_num < len(providers):
                            p = providers[toggle_num]
                            if p in visible_providers:
                                visible_providers.discard(p)
                            else:
                                visible_providers.add(p)
                    elif lang_toggle:
                        lang_zh = not lang_zh
                    elif metric_toggle:
                        or_metric = _next_or_metric(or_metric)
                    elif days_toggle:
                        days_window = _next_days_window(days_window)
                    live.update(_build_panel(), refresh=True)
                await asyncio.sleep(0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Multi-Provider AI Quota Tracker CLI")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Interactive mode: h help, c config, ←/→ or [/] themes, r refresh, q quit")
    parser.add_argument("--provider", help="Comma-separated providers to query (kimi,openai,anthropic,openrouter)")
    parser.add_argument("--config", help="Custom configuration file path")
    parser.add_argument("--theme", help="Specify color theme: blue-dark, blue-light, sky-dark, salmon-dark, turquoise-dark, pink-light, violet-dark, amber-dark, mint-dark, monochrome, blind-deuteranopia, blind-tritanopia")
    parser.add_argument("--serve", action="store_true", help="Start web server instead of CLI output")
    parser.add_argument("--port", type=int, default=8765, help="Web server port (default: 8765)")
    args = parser.parse_args()

    resolver = ConfigResolver(config_path=args.config)
    config = resolver.resolve()

    # Serve mode: start web server
    if args.serve:
        await run_server(port=args.port, lang_zh=IS_ZH)
        return

    # Determine theme
    theme_name = args.theme if args.theme else config.theme

    # If --provider filter is provided, override enabled providers
    allowed_providers = None
    if args.provider:
        allowed_providers = [p.strip().lower() for p in args.provider.split(",") if p.strip()]
        # Filter config providers
        for p in list(config.providers.keys()):
            if p not in allowed_providers:
                config.providers[p].api_key = None

    # Interactive mode: hand off to TUI loop (handles its own dispatch)
    if args.interactive:
        await _interactive_mode(config, theme_name, config_path=str(resolver.config_path))
        return

    results, errors = await dispatch_all(config)

    # Filter outputs
    if allowed_providers:
        results = {k: v for k, v in results.items() if k in allowed_providers}
        errors = {k: v for k, v in errors.items() if k in allowed_providers}

    if args.json:
        output_data = {}
        for p, items in results.items():
            output_data[p] = [
                {
                    "label": item.label,
                    "used": item.used,
                    "limit": item.limit,
                    "remaining": item.remaining,
                    "percent": item.percent,
                    "reset_at": item.reset_at,
                    "unit": item.unit
                }
                for item in items
            ]
        # Include errors in JSON if any
        if errors:
            output_data["errors"] = errors
        print(json.dumps(output_data, ensure_ascii=False))
    elif args.plain:
        if not results and not errors:
            print(L["no_data"])
        else:
            for p in config.provider_order:
                items = results.get(p)
                if items:
                    for item in items:
                        if item.limit is not None and item.limit > 0:
                            pct_used = item.used / item.limit * 100
                            print(f"{p.capitalize()} - {item.label}: {item.used}/{item.limit} ({pct_used:.0f}% used)")
                        else:
                            if item.unit == "text":
                                if item.text_value:
                                    print(f"{p.capitalize()} - {item.label}: {item.text_value}")
                                else:
                                    print(f"{p.capitalize()} - {item.label}")
                            else:
                                print(f"{p.capitalize()} - {item.label}: {item.used} ({item.unit})")
            for p in config.provider_order:
                err = errors.get(p)
                if err:
                    print(f"{p.capitalize()} - Error: {err}", file=sys.stderr)
    else:
        console = Console()
        if not results and not errors:
            console.print(Panel(Text(L["no_data"], style="dim"), title=f"[bold]{L['title']}[/bold]"))
        else:
            display_order = config.provider_order
            if config.visible_providers is not None:
                display_order = [p for p in config.provider_order if p in config.visible_providers]
            or_metric = _parse_or_metric(config.or_metric)
            days_window = _parse_days_window(config.days_window)
            console.print(Panel(_format_aggregated_results(results, errors, display_order, theme_name, enabled_providers=set(config.enabled_providers), or_metric=or_metric, days_window=days_window), title=f"[bold]{L['title']}[/bold]", expand=True, padding=(1, 2, 1, 2)))

def run_cli():
    asyncio.run(main())

if __name__ == "__main__":
    run_cli()
