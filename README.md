<pre align="center">
 ██╗  ██╗ ██╗ ███╗   ███╗ ██╗     ██████╗  ██████╗  ██████╗  ███████╗
 ██║ ██╔╝ ██║ ████╗ ████║ ██║    ██╔════╝ ██╔═══██╗ ██╔══██╗ ██╔════╝
 █████╔╝  ██║ ██╔████╔██║ ██║    ██║      ██║   ██║ ██║  ██║ █████╗
 ██╔═██╗  ██║ ██║╚██╔╝██║ ██║    ██║      ██║   ██║ ██║  ██║ ██╔══╝
 ██║  ██╗ ██║ ██║ ╚═╝ ██║ ██║    ╚██████╗ ╚██████╔╝ ██████╔╝ ███████╗
 ╚═╝  ╚═╝ ╚═╝ ╚═╝     ╚═╝ ╚═╝     ╚═════╝  ╚═════╝  ╚═════╝  ╚══════╝
</pre>

> **English** · [中文](README.zh.md)

# Kimi Code Usage: The Curated Toolchain

**Manifesting your AI quota with aesthetic precision across CLI, MCP, and VS Code.**

![CLI & MCP (Python) Coverage](https://img.shields.io/badge/CLI%20%26%20MCP%20(Python)-100%25%20coverage-brightgreen)
![VS Code Extension Coverage](https://img.shields.io/badge/VS%20Code%20Extension-100%25%20coverage-brightgreen)

---

### 🌟 Project Vision

In the era of "Vibecoding," transparency of resources is a prerequisite for flow. **Kimi Code Usage** is a meticulously crafted toolchain — three components, one soul.

> **⚠️ 重要：API Key 类型说明**
>
> 本工具查询的是 **Kimi Code 平台（Coding Plan 会员）** 的用量数据。你需要的是 **Kimi Code 控制台** 创建的 API Key（格式 `sk-kimi-xxx`），
> **不是** Kimi 开放平台（platform.kimi.com）的 API Key（格式 `sk-xxx`）。两种 Key 不互通。
>
> 获取方式：登录 Kimi Code 控制台 → 创建 API Key → 设置环境变量 `KIMI_API_KEY`。
> 详见 [Kimi Code 文档](https://www.kimi.com/code/docs/)。

**Prerequisite:** A [Kimi Coding Plan](https://api.kimi.com/coding/v1) API Key (`sk-kimi-xxx`), set as `KIMI_API_KEY` in your environment or `.env` file.

> Monthly membership usage is optional. In interactive mode, if an installed Kimi WebBridge daemon is stopped, `kimi-usage` asks on every launch whether to start it. Declining affects only monthly credits. The browser extension must still be connected and Kimi must be logged in; weekly and 5-hour Kimi usage continue working when monthly usage is unavailable.

> ChatGPT Plus usage reads the local Codex authentication file. After a 401 response, it refreshes the access token and retries once. If authentication still fails, run `codex login`.

---

### ⚡ CLI Reporter

> A Rich-rendered panel in your terminal. Zero noise, pure signal.

**Install & Run:**
```bash
pip install kimi-code-usage
kimi-usage              # Aesthetic Rich panel
kimi-usage -i           # Interactive panel with optional WebBridge startup prompt
kimi-usage --json       # Machine-readable JSON
kimi-usage --plain      # Plain text output
```

Or run instantly without installing:
```bash
uvx kimi-code-usage
```

---

### 🔍 MCP Server

> Exposes `get_kimi_usage` to any MCP-compatible AI Agent.

Compatible with **Claude Code, Cursor, Windsurf, Hermes**, and any MCP-enabled agent.

**Add to your MCP config** (e.g., `~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "kimi-code-usage": {
      "command": "uvx",
      "args": ["--from", "kimi-code-usage", "kimi-mcp"],
      "env": {
        "KIMI_API_KEY": "YOUR_KEY"
      }
    }
  }
}
```

> **Note:** The MCP server still needs `--from` because `kimi-mcp` is a separate command from the default `kimi-code-usage` entry point.

Then simply ask your AI: *"Check my Kimi quota."*

---

### 💎 VS Code Extension

> A sleek status bar indicator with sensory color alerting.

**Install:** Search `Kimi Code Usage` in the VS Code Marketplace, or:
```bash
code --install-extension HainingYu.kimi-code-usage
```

**Configure** (`Settings > Kimi Code Usage`):

| Setting | Description | Default |
| :--- | :--- | :--- |
| `kimiCodeUsage.apiKey` | API key (or reads `KIMI_CODING_API_KEY`/`KIMI_API_KEY` env) | `""` |
| `kimiCodeUsage.baseUrl` | API Base URL | `"https://api.kimi.com/coding/v1"` |
| `kimiCodeUsage.refreshIntervalMinutes` | Auto-refresh interval in minutes | `5` |
| `kimiCodeUsage.weeklyLowThresholdPercent` | Weekly low quota warning threshold (%) | `30` |
| `kimiCodeUsage.fiveHourLowThresholdPercent` | 5-hour low quota warning threshold (%) | `15` |
| `kimiCodeUsage.showPaceIndicator` | Show pace indicator (Fast/Normal/Slow) | `true` |
| `kimiCodeUsage.showPaceBar` | Show pace bar in status bar | `true` |

**Usage:** Status bar shows `🌕  [===]  Wee:96% 5Ho:99%`. Hover for details. `Cmd+Shift+P → Kimi: Refresh`.

---

## 📊 Real-World Analysis

> *How much does a ¥199/mo Coding Plan actually cover? Real data from 5 months of heavy vibe coding, with a cost comparison against standard API pricing.*

**Full data → [`docs/kimi-code-usage.md`](docs/kimi-code-usage.md)**

### 1. Profile

| Item | Detail |
|:---|:---|
| Plan | Tier 3 Allegretto ($31/mo) → **¥199/mo** |
| Workflow | Claude Code + kimi-for-coding, heavy vibe coding |
| Data Period | 2026-01 ~ 2026-05 full records (~3,152M tokens) |

### 2. Token Composition

| Component | 5-Month Total | Share |
|:---|:---|---:|
| Input (Cache Miss) | ~154M | 4.9% |
| Cache Created | ~89M | 2.8% |
| Output | ~12M | 0.4% |
| **Cache Read (Cache Hit)** | **~2,896M** | **91.9%** |
| **Total** | **~3,152M** | **100%** |

A **91.9% cache hit rate** is the signature of vibe coding — long sessions where each turn carries full conversation history, and only the latest exchange is fresh.

### 3. Actual Monthly Burn

Based on continuous weekly sampling (3 days = 30% of weekly quota):

| Metric | Value |
|:---|:---:|
| Weekly Burn | ~320M tokens |
| **Monthly Burn** | **≈ 1.37 ~ 1.5 billion tokens** |
| Plan Cost | ¥199/mo |
| **Effective Rate** | **≈ ¥0.14 / million tokens** |

### 4. Cost Comparison

Priced against **Kimi K2.6 standard API rates** (input ¥6.50 / cache ¥1.10 / output ¥27.00 per million tokens):

| Scenario | Cost/Month | Multiple |
|:---|:---:|:---:|
| **Kimi Coding Plan (¥199)** | **¥199** | **1×** |
| Pay-as-you-go (K2.6 standard) | **≈ ¥2,420** | **12.2×** |

| Pay-as-you-go Breakdown | Volume/Month | Rate | Cost |
|:---|---:|:---:|---:|
| Input (Cache Miss) | 73.5M | ¥6.50/MTok | ¥478 |
| Cache Read (Hit) | 1,378.5M | ¥1.10/MTok | ¥1,516 |
| Output | 5.55M | ¥27.00/MTok | ¥150 |
| Cache Created | 42.5M | ¥6.50/MTok | ¥276 |
| **Total** | **1.5B** | | **¥2,420** |

### 5. Bottom Line

> **The Coding Plan saves heavy users ≈ ¥2,221/month (~92%).** Cache reads account for 92% of total tokens; the plan bundles both cache and input into the subscription fee. Under pay-as-you-go, cache alone makes up 63% of the bill.

### ⚠️ Disclaimer

> This analysis reflects one user's actual usage from 2026-01 to 2026-05 via `ccusage`. Token ratios and cost estimates are for **reference only** — actual results vary by session pattern, model choice, caching behavior, and API pricing. Rates sourced from [platform.kimi.com](https://platform.kimi.com) as of 2026-05-24.

---

### 🎨 About the Curator

Crafted with ❤️ by **Haining Yu**, an Art Curator and Vibecoder. This toolchain is part of a curated collection designed to bridge the gap between aesthetic curation and intuitive, AI-powered coding.

---

<p align="center">
  <strong>Enjoy the flow. Stay in the vibe.</strong>
</p>
