import argparse
import asyncio
import json
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from typing import Dict, List

from kimi_code_usage.config import ConfigResolver
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

def _get_localized_label(label: str) -> str:
    if label == "Weekly Usage":
        return L["weekly_limit"]
    if "Limit" in label:
        return label.replace("Limit", L["limit_fallback"])
    return label

def _format_aggregated_results(results: Dict[str, List[ProviderUsage]], errors: Dict[str, str]) -> Text:
    result = Text()
    order = ["kimi", "openai", "anthropic", "openrouter"]
    first_section = True

    for p in order:
        p_items = results.get(p)
        if not p_items:
            continue

        if not first_section:
            result.append("\n\n")
        first_section = False

        title_str = "Kimi" if p == "kimi" else p.capitalize()
        result.append(f"── {title_str} ──────────────────────\n", style="bold cyan")

        visual_widths = [_get_visual_width(_get_localized_label(r.label)) for r in p_items]
        max_visual_width = max(visual_widths) if visual_widths else 0
        max_visual_width = max(max_visual_width, 6)
        bar_width = 20

        for i, row in enumerate(p_items):
            if i > 0:
                result.append("\n")

            loc_label = _get_localized_label(row.label)
            label_v_width = _get_visual_width(loc_label)
            padding = " " * (max_visual_width - label_v_width)

            result.append(f"  {loc_label}{padding}  ", style="cyan")

            if row.limit is not None and row.limit > 0:
                used_ratio = row.used / row.limit
                remaining_percent = max(0.0, 100.0 - (used_ratio * 100.0))
                color = "red" if used_ratio > 0.9 else "yellow" if used_ratio > 0.7 else "green"
                filled = min(bar_width, int(used_ratio * bar_width))

                result.append("█" * filled, style=color)
                result.append("░" * (bar_width - filled))

                if row.unit == "%":
                    result.append(f"  {used_ratio * 100:.0f}%   {remaining_percent:.0f}% {L['remaining']}", style="bold")
                elif row.unit == "$":
                    result.append(f"  ${row.used:.2f} / ${row.limit:.2f} ({remaining_percent:.0f}% {L['remaining']})", style="bold")
                else:
                    result.append(f"  {row.used:,.0f} / {row.limit:,.0f} {row.unit} ({remaining_percent:.0f}% {L['remaining']})", style="bold")
            else:
                if row.unit == "$":
                    result.append(f"  ${row.used:.2f}", style="bold")
                elif row.unit == "text":
                    # For messages like "API Plan" where label itself is descriptive
                    pass
                else:
                    result.append(f"  {row.used:,.0f} {row.unit}", style="bold")

            meta_parts = []
            if row.countdown:
                meta_parts.append(f"{L['countdown']}: {row.countdown}")
            if row.reset_at:
                meta_parts.append(f"{L['reset']}: {row.reset_at}")
            if meta_parts:
                result.append("\n")
                result.append("  " + "  ".join(meta_parts), style="dim cyan")

    for p, err in errors.items():
        if not first_section:
            result.append("\n\n")
        first_section = False
        title_str = "Kimi" if p == "kimi" else p.capitalize()
        result.append(f"── {title_str} ──────────────────────\n", style="bold red")
        result.append(f"  ⚠ {err}", style="bold red")

    return result

async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Multi-Provider AI Quota Tracker CLI")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("--provider", help="Comma-separated providers to query (kimi,openai,anthropic,openrouter)")
    parser.add_argument("--config", help="Custom configuration file path")
    args = parser.parse_args()

    resolver = ConfigResolver(config_path=args.config)
    config = resolver.resolve()

    # If --provider filter is provided, override enabled providers
    allowed_providers = None
    if args.provider:
        allowed_providers = [p.strip().lower() for p in args.provider.split(",") if p.strip()]
        # Filter config providers
        for p in list(config.providers.keys()):
            if p not in allowed_providers:
                config.providers[p].api_key = None

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
            for p, items in results.items():
                for item in items:
                    if item.limit is not None and item.limit > 0:
                        pct_used = item.used / item.limit * 100
                        print(f"{p.capitalize()} - {item.label}: {item.used}/{item.limit} ({pct_used:.0f}% used)")
                    else:
                        if item.unit == "text":
                            print(f"{p.capitalize()} - {item.label}")
                        else:
                            print(f"{p.capitalize()} - {item.label}: {item.used} ({item.unit})")
            for p, err in errors.items():
                print(f"{p.capitalize()} - Error: {err}", file=sys.stderr)
    else:
        console = Console()
        if not results and not errors:
            console.print(Panel(Text(L["no_data"], style="dim"), title=f"[bold]{L['title']}[/bold]"))
        else:
            console.print(Panel(_format_aggregated_results(results, errors), title=f"[bold]{L['title']}[/bold]", expand=False, padding=(1, 2, 1, 2)))

def run_cli():
    asyncio.run(main())

if __name__ == "__main__":
    run_cli()
