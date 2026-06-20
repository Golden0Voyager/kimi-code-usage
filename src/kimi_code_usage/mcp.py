from fastmcp import FastMCP

from kimi_code_usage.config import ConfigResolver
from kimi_code_usage.providers import ProviderUsage, dispatch_all

# Initialize FastMCP for Kimi Code Usage
mcp = FastMCP("Kimi Code Usage")

L = {
    "error_key": "No API keys configured. Please set environment variables (e.g. KIMI_API_KEY) or configure ~/.kimi-usage/config.json",
    "no_data": "No usage data found.",
}

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


def _format_activity_lines(item: ProviderUsage, provider_title: str, metric: str = "requests") -> list[str]:
    lines = []
    if item.activity_totals:
        t = item.activity_totals
        parts = [f"{t.requests:,.0f} requests"]
        tok = f"In: {_format_tokens(t.prompt_tokens)} / Out: {_format_tokens(t.completion_tokens)}"
        if t.reasoning_tokens:
            tok += f" (+ {_format_tokens(t.reasoning_tokens)} reason)"
        parts.append(tok)
        parts.append(f"Spend: ${t.spend:.2f}")
        lines.append(f"{provider_title} - Activity: {' | '.join(parts)}")

    if item.daily_activity:
        metric_label = metric.capitalize()
        lines.append(f"{provider_title} - Daily {metric_label}:")
        if metric == "requests":
            max_val = max(sum(m.requests for m in d.models) for d in item.daily_activity) or 1.0
            for day in item.daily_activity[-14:]:
                bar_len = int(sum(m.requests for m in day.models) / max_val * 20) if max_val > 0 else 0
                date = day.date[5:10] if len(day.date) >= 10 else day.date
                lines.append(f"  {date} {'█' * bar_len}{'·' * (20 - bar_len)} {sum(m.requests for m in day.models):,.0f}")
        elif metric == "tokens":
            max_val = max(sum(m.prompt_tokens + m.completion_tokens + m.reasoning_tokens for m in d.models) for d in item.daily_activity) or 1.0
            for day in item.daily_activity[-14:]:
                val = sum(m.prompt_tokens + m.completion_tokens + m.reasoning_tokens for m in day.models)
                bar_len = int(val / max_val * 20) if max_val > 0 else 0
                date = day.date[5:10] if len(day.date) >= 10 else day.date
                lines.append(f"  {date} {'█' * bar_len}{'·' * (20 - bar_len)} {_format_tokens(val)}")
        else:
            max_val = max(d.total for d in item.daily_activity) or 1.0
            for day in item.daily_activity[-14:]:
                bar_len = int(day.total / max_val * 20) if max_val > 0 else 0
                date = day.date[5:10] if len(day.date) >= 10 else day.date
                lines.append(f"  {date} {'█' * bar_len}{'·' * (20 - bar_len)} ${day.total:.2f}")

    if item.top_models:
        lines.append(f"{provider_title} - Top Models:")
        for m in item.top_models[:7]:
            name = _model_short_name(m.model)
            if metric == "requests":
                val_str = f"{m.requests:,.0f} req"
            elif metric == "tokens":
                val_str = _format_tokens(m.prompt_tokens + m.completion_tokens + m.reasoning_tokens)
            else:
                val_str = f"${m.spend:.2f}"
            lines.append(f"  {name}: {val_str}")

    return lines


@mcp.tool()
async def get_usage(provider: str | None = None) -> str:
    """
    Get API usage/quota from configured LLM providers.
    获取已配置的 LLM 服务商的 API 使用量与配额限制。

    Args:
        provider: Optional filter - "kimi", "openai", "anthropic", "openrouter", or comma-separated list.
    """
    resolver = ConfigResolver()
    config = resolver.resolve()

    allowed = None
    if provider:
        allowed = [p.strip().lower() for p in provider.split(",") if p.strip()]
        for p in list(config.providers.keys()):
            if p not in allowed:
                config.providers[p].api_key = None

    if not config.enabled_providers:
        return L["error_key"]

    try:
        results, errors = await dispatch_all(config)

        if allowed:
            results = {k: v for k, v in results.items() if k in allowed}
            errors = {k: v for k, v in errors.items() if k in allowed}

        if not results and not errors:
            return L["no_data"]

        lines = []
        order = config.provider_order

        for p in order:
            p_items = results.get(p)
            if not p_items:
                continue
            for item in p_items:
                provider_title = "Kimi" if p == "kimi" else p.capitalize()

                # Structured OpenRouter activity data
                if item.activity_totals or item.daily_activity or item.top_models:
                    lines.extend(_format_activity_lines(item, provider_title))
                    continue

                if item.unit == "text":
                    if item.text_value:
                        line = f"{provider_title} - {item.label}: {item.text_value}"
                    else:
                        line = f"{provider_title} - {item.label}"
                else:
                    line = f"{provider_title} - {item.label}: "

                if item.limit is not None and item.limit > 0:
                    pct_rem = max(0.0, 100.0 - (item.used / item.limit * 100.0))
                    if item.unit == "$":
                        line += f"${item.used:.2f}/${item.limit:.2f} used ({pct_rem:.0f}% remaining)"
                    else:
                        line += f"{item.used:,.0f}/{item.limit:,.0f} used ({pct_rem:.0f}% remaining)"
                else:
                    if item.unit == "$":
                        line += f"${item.used:.2f} used"
                    elif item.unit == "text":
                        # For text unit, label already printed above
                        pass
                    else:
                        line += f"{item.used:,.0f} used ({item.unit})"

                if item.countdown and item.reset_at:
                    line += f" | Reset in {item.countdown} (at {item.reset_at})"
                lines.append(line)

        for p in order:
            err = errors.get(p)
            if err:
                provider_title = "Kimi" if p == "kimi" else p.capitalize()
                lines.append(f"{provider_title} - Error: {err}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching usage: {str(e)}"

@mcp.tool()
async def get_kimi_usage() -> str:
    """
    Get the current Kimi Coding Plan API usage and quota limits.
    获取当前 Kimi Coding Plan API 的使用量和配额限制。
    """
    return await get_usage("kimi")

def run_mcp():
    mcp.run()

if __name__ == "__main__":
    run_mcp()
