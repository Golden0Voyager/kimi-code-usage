import os
from fastmcp import FastMCP
from kimi_code_usage.config import ConfigResolver
from kimi_code_usage.providers import dispatch_all

# Initialize FastMCP for Kimi Code Usage
mcp = FastMCP("Kimi Code Usage")

L = {
    "error_key": "No API keys configured. Please set environment variables (e.g. KIMI_API_KEY) or configure ~/.kimi-usage/config.json",
    "no_data": "No usage data found.",
}

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
        order = ["kimi", "openai", "anthropic", "openrouter"]

        for p in order:
            p_items = results.get(p)
            if not p_items:
                continue
            for item in p_items:
                provider_title = "Kimi" if p == "kimi" else p.capitalize()
                
                if item.unit == "text":
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

        for p, err in errors.items():
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
