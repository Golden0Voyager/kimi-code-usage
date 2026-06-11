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
from typing import Dict, List, Optional, Tuple

from kimi_code_usage.config import ConfigResolver, save_theme
from kimi_code_usage.providers import dispatch_all, ProviderUsage

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

def _get_visual_width(s: str) -> int:
    import unicodedata
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ("W", "F", "A"):
            width += 2
        else:
            width += 1
    return width

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
        }
        if label in translations:
            return translations[label]

    # 2. Standard rule replacements
    if label == "Weekly Usage":
        return _L["weekly_limit"]
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
    return text_val

# (typing already imported at top)

THEME_MAP = {
    # ── Matisse-inspired: cobalt blue on dark, vivid & flat ──
    "default-dark": {
        "title": "bold dodger_blue2",
        "label": "cornflower_blue",
        "meta": "grey62",
        "ok": "medium_spring_green",
        "warning": "gold1",
        "danger": "indian_red1",
    },
    # ── Matisse-inspired: warm cadmium tones on light bg ──
    "default-light": {
        "title": "bold blue",
        "label": "dark_blue",
        "meta": "grey35",
        "ok": "dark_green",
        "warning": "dark_orange",
        "danger": "red3",
    },
    # ── Matisse: cobalt + viridian — Jazz interior palette ──
    "matisse-dark": {
        "title": "bold royal_blue1",
        "label": "sky_blue1",
        "meta": "grey58",
        "ok": "spring_green2",
        "warning": "orange1",
        "danger": "light_coral",
    },
    # ── Matisse: warm coral & saffron — Fauve warmth ──
    "matisse-warm": {
        "title": "bold light_salmon3",
        "label": "sandy_brown",
        "meta": "grey46",
        "ok": "dark_sea_green2",
        "warning": "gold3",
        "danger": "indian_red",
    },
    # ── Matisse: deep viridian on near-black — La Musique ──
    "viridian-dark": {
        "title": "bold turquoise2",
        "label": "medium_aquamarine",
        "meta": "grey53",
        "ok": "aquamarine1",
        "warning": "khaki1",
        "danger": "hot_pink",
    },
    # ── Matisse: rose madder & ivory — Odalisque tones ──
    "odalisque-light": {
        "title": "bold deep_pink3",
        "label": "hot_pink3",
        "meta": "grey37",
        "ok": "dark_cyan",
        "warning": "dark_goldenrod",
        "danger": "red3",
    },
    # ── High-contrast monochrome — for any terminal ──
    "monochrome": {
        "title": "bold white",
        "label": "white",
        "meta": "grey46",
        "ok": "white",
        "warning": "grey74",
        "danger": "bold reverse",
    },
    # ── Accessibility: Deuteranopia (red-green blind) ──
    # Uses blue/yellow contrast — no reliance on red or green
    "deuteranopia": {
        "title": "bold dodger_blue1",
        "label": "cornflower_blue",
        "meta": "grey62",
        "ok": "dodger_blue1",
        "warning": "gold1",
        "danger": "dark_orange",
    },
    # ── Accessibility: Tritanopia (blue-yellow blind) ──
    # Uses red/green/magenta contrast — no reliance on blue or yellow
    "tritanopia": {
        "title": "bold red1",
        "label": "light_coral",
        "meta": "grey62",
        "ok": "chartreuse3",
        "warning": "pale_green3",
        "danger": "bold red1",
    },
}


def _handle_key(ch: str, idx: int, n: int) -> Tuple[int, bool, bool, Optional[int], bool]:
    """Map a keypress to a TUI action.

    Returns:
        (new_idx, should_quit, should_refresh, toggle_provider_num, lang_toggle)
    """
    if ch in ('q', 'Q', '\x03', '\x04'):       # q  Ctrl-C  Ctrl-D
        return idx, True, False, None, False
    if ch in (']', 'n', '\t', '\x1b[C'):        # ]  n  Tab  →
        return (idx + 1) % n, False, False, None, False
    if ch in ('[', 'p', '\x1b[D'):              # [  p  ←
        return (idx - 1) % n, False, False, None, False
    if ch in ('r', 'R'):                        # r → refresh data
        return idx, False, True, None, False
    if ch in ('1', '2', '3', '4'):              # 1-4 → toggle provider panel
        return idx, False, False, int(ch) - 1, False
    if ch in ('l', 'L'):                        # l → toggle language zh/en
        return idx, False, False, None, True
    return idx, False, False, None, False


def _format_aggregated_results(
    results: Dict[str, List[ProviderUsage]],
    errors: Dict[str, str],
    order: Optional[List[str]] = None,
    theme_name: str = "default-dark",
    lang_zh: bool = IS_ZH,
) -> Text:
    _L = L_ZH if lang_zh else L_EN
    result = Text()
    if order is None:
        order = ["anthropic", "openai", "openrouter", "kimi"]

    theme = THEME_MAP.get(theme_name)
    if not theme:
        theme = THEME_MAP["default-dark"]
        
    for p in order:
        p_items = results.get(p)
        if not p_items:
            continue

        title_str = "Kimi" if p == "kimi" else p.capitalize()
        base_line = f"──── {title_str} "
        divider_line = base_line + "─" * max(2, 50 - len(base_line))
        result.append(f"{divider_line}\n", style=theme["title"])

        visual_widths = [_get_visual_width(_get_localized_label(r.label, lang_zh)) for r in p_items]
        max_visual_width = max(visual_widths) if visual_widths else 0
        max_visual_width = max(max_visual_width, 6)
        bar_width = 20

        for i, row in enumerate(p_items):
            if i > 0:
                result.append("\n")

            loc_label = _get_localized_label(row.label, lang_zh)
            label_v_width = _get_visual_width(loc_label)
            padding = " " * (max_visual_width - label_v_width)

            result.append(f"  {loc_label}{padding}  ", style=theme["label"])

            if row.limit is not None and row.limit > 0:
                used_ratio = row.used / row.limit
                remaining_percent = max(0.0, 100.0 - (used_ratio * 100.0))
                color = theme["danger"] if used_ratio > 0.9 else theme["warning"] if used_ratio > 0.7 else theme["ok"]
                filled = min(bar_width, int(used_ratio * bar_width))

                result.append("█" * filled, style=color)
                result.append("·" * (bar_width - filled), style="grey50")

                if row.unit == "%":
                    result.append(f"  {used_ratio * 100:.0f}%   {remaining_percent:.0f}% {_L['remaining']}", style="bold")
                elif row.unit == "$":
                    result.append(f"  ${row.used:.2f} / ${row.limit:.2f} ({remaining_percent:.0f}% {_L['remaining']})", style="bold")
                else:
                    result.append(f"  {row.used:,.0f} / {row.limit:,.0f} {row.unit} ({remaining_percent:.0f}% {_L['remaining']})", style="bold")
            else:
                if row.unit == "$":
                    result.append(f"  ${row.used:.2f}", style="bold")
                elif row.unit == "text":
                    if row.text_value:
                        loc_val = _get_localized_text_value(row.text_value, lang_zh)
                        result.append(f"  {loc_val}", style="bold")
                else:
                    result.append(f"  {row.used:,.0f} {row.unit}", style="bold")

            meta_parts = []
            if row.countdown:
                meta_parts.append(f"{_L['countdown']}: {row.countdown}")
            if row.reset_at:
                meta_parts.append(f"{_L['reset']}: {row.reset_at}")
            if meta_parts:
                result.append("\n")
                result.append("  " + "  ".join(meta_parts), style=theme["meta"])

        result.append("\n\n")

    for p, err in errors.items():
        title_str = "Kimi" if p == "kimi" else p.capitalize()
        base_line = f"──── {title_str} "
        divider_line = base_line + "─" * max(2, 50 - len(base_line))
        result.append(f"{divider_line}\n", style=theme["danger"])
        result.append(f"  ⚠ {err}", style=theme["danger"])
        result.append("\n\n")

    return result


async def _interactive_mode(config: "AppConfig", initial_theme: str) -> None:
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

    results: Dict[str, List[ProviderUsage]] = {}
    errors: Dict[str, str] = {}

    # Determine initial visible providers and language
    if config.visible_providers is not None:
        visible_providers: set = set(p for p in config.visible_providers if p in config.provider_order)
    else:
        visible_providers: set = set(config.provider_order)

    if config.language == "zh":
        lang_zh: bool = True
    elif config.language == "en":
        lang_zh: bool = False
    else:
        lang_zh: bool = IS_ZH

    saved_notice: list = [None]   # holds the saved theme name briefly, then None

    _SHORT = {
        "anthropic": "Claude", "openai": "GPT",
        "openrouter": "OR",    "kimi": "Kimi",
    }

    def _build_panel() -> Panel:
        visible_order = [p for p in config.provider_order if p in visible_providers]
        _L = L_ZH if lang_zh else L_EN
        body = _format_aggregated_results(results, errors, visible_order, themes[idx], lang_zh)

        top_bar = Text()
        # Theme name
        top_bar.append(" 主题: " if lang_zh else " theme: ", style="dim")
        top_bar.append(themes[idx], style="bold")
        top_bar.append("  │  ", style="dim")
        # Provider toggles
        for i, p in enumerate(config.provider_order, 1):
            short = _SHORT.get(p, p[:4].title())
            if p in visible_providers:
                top_bar.append(f"[{i}]", style="bold")
                top_bar.append(f"{short}● ", style="dim")
            else:
                top_bar.append(f"[{i}]", style="dim")
                top_bar.append(f"{short}○ ", style="dim italic")
        top_bar.justify = "center"

        hint = Text()
        # Keybindings
        hint.append("[q]", style="bold red")
        hint.append(" 退出  " if lang_zh else " quit  ", style="dim")
        hint.append("[r]", style="bold")
        hint.append(" 刷新  " if lang_zh else " refresh  ", style="dim")
        hint.append("[←/→]", style="bold")
        hint.append(" 主题  " if lang_zh else " theme  ", style="dim")
        hint.append("[1-4]", style="bold")
        hint.append(" 面板  " if lang_zh else " panels  ", style="dim")
        hint.append("[l]", style="bold")
        hint.append(" EN" if lang_zh else " 中文", style="dim")
        hint.append("  ", style="dim")
        hint.append("[⏎]", style="bold")
        hint.append(" 保存主题" if lang_zh else " Save theme", style="dim")
        if saved_notice[0]:
            hint.append(f"  ✓ {'已保存' if lang_zh else 'Saved'}: {saved_notice[0]}", style="bold green")
        hint.justify = "center"

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
    try:
        tty.setcbreak(fd)
        results, errors = await dispatch_all(config)
        console = Console()
        with Live(_build_panel(), console=console, refresh_per_second=4) as live:
            running = True
            while running:
                rlist, _, _ = _select_module.select([sys.stdin], [], [], 0.15)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch == '\x1b':
                        r2, _, _ = _select_module.select([sys.stdin], [], [], 0.05)
                        if r2:
                            ch2 = sys.stdin.read(1)
                            if ch2 == '[':
                                r3, _, _ = _select_module.select([sys.stdin], [], [], 0.05)
                                if r3:
                                    ch3 = sys.stdin.read(1)
                                    ch = f'\x1b[{ch3}'
                    if saved_notice[0]:     # clear notice on any new keypress
                        saved_notice[0] = None
                    if ch in ('\r', '\n'):  # Enter → save settings to config file
                        save_theme(
                            themes[idx],
                            language="zh" if lang_zh else "en",
                            visible_providers=list(visible_providers)
                        )
                        saved_notice[0] = themes[idx]
                        live.update(_build_panel())
                        continue
                    idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(ch, idx, len(themes))
                    if quit_flag:
                        running = False
                    elif refresh_flag:
                        results, errors = await dispatch_all(config)
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
                    live.update(_build_panel())
                await asyncio.sleep(0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Multi-Provider AI Quota Tracker CLI")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Interactive mode: ←/→ or [/] to cycle themes, r refresh, q quit")
    parser.add_argument("--provider", help="Comma-separated providers to query (kimi,openai,anthropic,openrouter)")
    parser.add_argument("--config", help="Custom configuration file path")
    parser.add_argument("--theme", help="Specify color theme: default-dark, default-light, matisse-dark, matisse-warm, viridian-dark, odalisque-light, monochrome, deuteranopia, tritanopia")
    args = parser.parse_args()

    resolver = ConfigResolver(config_path=args.config)
    config = resolver.resolve()

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
        await _interactive_mode(config, theme_name)
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
            console.print(Panel(_format_aggregated_results(results, errors, config.provider_order, theme_name), title=f"[bold]{L['title']}[/bold]", expand=True, padding=(1, 2, 1, 2)))

def run_cli():
    asyncio.run(main())

if __name__ == "__main__":
    run_cli()
