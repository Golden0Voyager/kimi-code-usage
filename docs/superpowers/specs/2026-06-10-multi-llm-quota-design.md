# Multi-Provider Quota Query Integration Design

> Extend kimi-code-usage to support OpenAI, Anthropic, and OpenRouter quota/usage queries alongside the existing Kimi API.

## 1. Goal

Allow users to query usage/quota from multiple LLM providers (Kimi, OpenAI, Anthropic, OpenRouter) through a unified CLI interface and MCP server, with a single config file or environment variables.

## 2. Architecture

```
User Config (env vars + ~/.kimi-usage/config.json)
                    │
                    ▼
         ┌──────────────────┐
         │ ConfigResolver   │ ← reads all available keys
         └────────┬─────────┘
                  │
         ┌────────┴─────────┐
         │ ProviderRegistry │ ← determines which providers to query
         └────────┬─────────┘
                  │
         ┌────────┴─────────┐
         │ BatchDispatcher  │ ← parallel fetch from all enabled providers
         │                  │
    ┌────┼────┐    ┌───────┼──────┐    ┌────────┼───────┐
    ▼    ▼    ▼    ▼       ▼      ▼    ▼        ▼       ▼
  Kimi OpenAI Claude OpenRouter  ... (future providers)
    │    │    │    │       │      │    │        │       │
    └────┼────┴────┼───────┴──────┼────┴────────┼───────┘
         │         │              │
         ▼         ▼              ▼
    ┌─────────────────────────────────┐
    │    UsageAggregator              │
    │  ┌───────────────────────────┐  │
    │  │ [Kimi]      W:96% 5H:99% │  │
    │  │ [OpenAI]    1.2M/10M tok │  │
    │  │ [Anthropic] 7d:45% 5h:12│  │
    │  │ [OpenRouter] $4.50/$10  │  │
    │  └───────────────────────────┘  │
    └────────────┬────────────────────┘
                 │
           ┌─────┴─────┐
           ▼           ▼
         CLI Panel    MCP Response
```

## 3. Components

### 3.1 ConfigResolver

**Responsibility:** Collect API keys from all sources.

| Source | Priority | Details |
|---|---|---|
| Environment variables | Highest | `KIMI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` |
| Config file | Medium | `~/.kimi-usage/config.json` |

Config file format:

```json
{
  "providers": {
    "kimi": { "apiKey": "sk-...", "baseUrl": "https://api.kimi.com/coding/v1" },
    "openai": { "apiKey": "sk-..." },
    "anthropic": { "apiKey": "sk-ant-..." },
    "openrouter": { "apiKey": "sk-or-..." }
  }
}
```

A provider is "enabled" if any valid key is found for it (env or config).

### 3.2 ProviderRegistry

**Responsibility:** Build a list of enabled providers from resolved config.

```python
def list_enabled_providers(config: dict) -> list[str]:
    """Returns provider IDs that have valid credentials."""
```

Returns: `["kimi", "openai", "anthropic", "openrouter"]` or a subset.

### 3.3 Provider Fetchers

Each provider has a standalone fetch function. Kimi keeps its existing logic untouched.

| Provider | Fetch Function | Endpoint | Returns |
|---|---|---|---|
| Kimi | `fetch_kimi_usage()` | `GET /usages` (existing) | `UsageItem[]` (weekly/5h) |
| OpenAI | `fetch_openai_usage()` | `GET /v1/organization/usage/completions` | tokens, cost |
| Anthropic | `fetch_anthropic_usage()` | `GET /api/oauth/usage` | 5h/7d utilization % |
| OpenRouter | `fetch_openrouter_usage()` | `GET /v1/auth/key` | credits remaining, total used |

**Unified data format:**

```python
@dataclass
class ProviderUsage:
    provider: str              # "kimi" | "openai" | "anthropic" | "openrouter"
    label: str                 # display name ("Weekly", "5 Hours", etc.)
    used: float
    limit: float | None        # None if unlimited
    remaining: float | None
    percent: float | None      # 0-100, None if no limit
    reset_at: str | None       # ISO timestamp
    unit: str                  # "%" | "tokens" | "$"
```

### 3.4 BatchDispatcher

**Responsibility:** Dispatch parallel fetch requests to all enabled providers.

```python
async def dispatch_all(config: Config) -> dict[str, list[ProviderUsage]]:
    """Fetch from all enabled providers concurrently."""
```

- Uses `asyncio.gather()` with timeout (10s per provider).
- Failed providers are reported as error entries, not blocking others.

### 3.5 UsageAggregator

**Responsibility:** Merge multiple provider results into a unified display model.

```python
@dataclass
class AggregatedResult:
    providers: dict[str, list[ProviderUsage]]  # provider_id → its items
    errors: dict[str, str]                     # provider_id → error message
```

### 3.6 CLI Display (Rich)

**Multi-card Panel layout:**

```
╭─────────────────────────────────────────╮
│         Kimi Code Usage                 │
├─────────────────────────────────────────┤
│                                         │
│  ┌── Kimi ──────────────────────┐       │
│  │  W: ████████░░ 96%           │       │
│  │  5H: ██████████░ 99%         │       │
│  │  Resets in 2d 14h            │       │
│  └──────────────────────────────┘       │
│                                         │
│  ┌── OpenAI ────────────────────┐       │
│  │  Tokens: 1,234,567 / 10M     │       │
│  │  Cost:   $4.50 this period   │       │
│  └──────────────────────────────┘       │
│                                         │
│  ┌── Anthropic ─────────────────┐       │
│  │  7-day: ████░░░░░░ 45%       │       │
│  │  5-hour: █░░░░░░░░░ 12%     │       │
│  └──────────────────────────────┘       │
│                                         │
│  ┌── OpenRouter ────────────────┐       │
│  │  Credits: $4.50 / $10.00     │       │
│  └──────────────────────────────┘       │
│                                         │
╰─────────────────────────────────────────╯
```

**Output modes:**

| Flag | Format | Use case |
|---|---|---|
| (default) | Rich Panel | Terminal display |
| `--json` | JSON string | Machine parsing |
| `--plain` | Plain text | Scripting |

**Provider filter:**

```bash
kimi-usage                          # all enabled providers
kimi-usage --provider openai        # only OpenAI
kimi-usage --provider kimi,openai   # multiple specific providers
```

### 3.7 MCP Server

The existing MCP tool `get_kimi_usage` is renamed and extended:

```python
@mcp.tool()
async def get_usage(provider: str | None = None) -> str:
    """
    Get API usage/quota from configured LLM providers.
    Args:
        provider: Optional filter - "kimi", "openai", "anthropic", "openrouter", or None for all
    """
```

Returns a formatted text summary of all requested providers.

## 4. API Details Per Provider

### Kimi (Existing - Unchanged)

- **Endpoint:** `GET {baseUrl}/usages`
- **Auth:** `Authorization: Bearer {apiKey}`
- **Response:** `{"usage": {...}, "limits": [...]}`
- **Windows:** Weekly (7d), 5-Hour
- **Docs:** https://platform.kimi.com

### OpenAI

- **Endpoint:** `GET https://api.openai.com/v1/organization/usage/completions`
- **Params:** `start_time`, `end_time`, `bucket_width=1d`, `limit=7`
- **Auth:** `Authorization: Bearer {apiKey}` (requires org admin key)
- **Response:** Token counts per bucket (input, output, cached)
- **Second endpoint:** `GET /v1/organization/usage/costs` for monetary costs
- **Fallback:** If admin key not available, return rate-limit headers from regular API calls as a basic indicator

### Anthropic

- **OAuth endpoint:** `GET https://api.anthropic.com/api/oauth/usage`
  - Returns: `five_hour.utilization`, `seven_day.utilization` (0-100%)
  - Requires: OAuth token (Claude Pro/Max/Team)
- **API Key fallback:** Anthropic doesn't expose a usage API for API-key-based accounts via a public endpoint. In this case, show "API plan - no usage endpoint available" or allow user to configure manually.

### OpenRouter

- **Endpoint:** `GET https://openrouter.ai/api/v1/auth/key`
- **Auth:** `Authorization: Bearer {apiKey}`
- **Response:**
  ```json
  {
    "data": {
      "label": "my-key",
      "usage": 450.0,
      "limit": 1000.0,
      "is_free": false
    }
  }
  ```
- **Units:** `usage` and `limit` are in USD credits
- **Also available:** Rate limit headers from regular API calls

## 5. Error Handling

| Scenario | Behavior |
|---|---|
| Provider key not found | Skip provider silently, show "not configured" |
| Provider API unreachable | Show `⚠ {provider}: API unreachable` |
| Rate limited (429) | Show `⚠ {provider}: Rate limited, retry after Xs` |
| Auth failure (401/403) | Show `⚠ {provider}: Invalid key or insufficient permissions` |
| Partial failure | Other providers still display normally |
| Timeout | Show `⚠ {provider}: Request timed out` |

## 6. Configuration

### `~/.kimi-usage/config.json`

```json
{
  "providers": {
    "kimi": {
      "apiKey": "",
      "baseUrl": "https://api.kimi.com/coding/v1"
    }
  },
  "general": {
    "refreshIntervalMinutes": 5,
    "outputMode": "rich"
  }
}
```

If `apiKey` is empty for a provider, the system falls back to the environment variable.

## 7. Files to Create/Modify

| File | Action | Description |
|---|---|---|
| `src/kimi_code_usage/config.py` | **Create** | Config loading and resolution (env + JSON) |
| `src/kimi_code_usage/providers/__init__.py` | **Create** | Provider registry, aggregator |
| `src/kimi_code_usage/providers/kimi.py` | **Create** | Kimi fetcher (extracted from main.py) |
| `src/kimi_code_usage/providers/openai.py` | **Create** | OpenAI fetcher |
| `src/kimi_code_usage/providers/anthropic.py` | **Create** | Anthropic fetcher |
| `src/kimi_code_usage/providers/openrouter.py` | **Create** | OpenRouter fetcher |
| `src/kimi_code_usage/main.py` | **Modify** | CLI entry point, multi-provider dispatch |
| `src/kimi_code_usage/mcp.py` | **Modify** | MCP tools, multi-provider support |
| `pyproject.toml` | **Modify** | Update CLI entry point if changed |
| `docs/superpowers/plans/2026-06-10-multi-llm-quota.md` | **Create** | Implementation plan later |

## 8. CLI API Surface

```bash
kimi-usage                          # All providers
kimi-usage --provider openai        # Single provider
kimi-usage --provider kimi,openai   # Multiple
kimi-usage --json                   # JSON output
kimi-usage --plain                  # Plain text
kimi-usage --config ~/custom.json   # Custom config path
```

## 9. Non-Goals (Out of Scope)

- VS Code extension changes (already excluded)
- Real-time token tracking / session watching (tokentop-style)
- Cost estimation from prompt/response (tokentop's pricing module)
- TUI dashboard with live refresh (tokentop's dashboard)
- Plugin system / SDK
- Historical data storage beyond what Kimi already has
