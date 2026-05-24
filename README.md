<p align="center">
  <img src="vscode-extension/assets/banner.png" width="100%" alt="Kimi Code Usage Banner">
</p>

> **English** · [中文](README.zh.md)

# Kimi Code Usage: The Curated Toolchain

**Manifesting your AI quota with aesthetic precision across CLI, MCP, and VS Code.**

---

### 🌟 Project Vision

In the era of "Vibecoding," transparency of resources is a prerequisite for flow. **Kimi Code Usage** is a meticulously crafted toolchain — three components, one soul.

**Prerequisite:** A [Kimi Coding Plan](https://api.kimi.com/coding/v1) API Key, set as `KIMI_API_KEY` in your environment or `.env` file.

---

### ⚡ CLI Reporter

> A Rich-rendered panel in your terminal. Zero noise, pure signal.

**Install & Run:**
```bash
pip install kimi-code-usage
kimi-usage              # Aesthetic Rich panel
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

**Configure** (`Settings > kimiUsage`):

| Setting | Description | Default |
| :--- | :--- | :--- |
| `apiKey` | API key (or reads `KIMI_API_KEY` env) | `""` |
| `refreshInterval` | Auto-refresh in minutes | `5` |
| `warnPercent` | Yellow caution threshold | `30%` |
| `criticalPercent` | Red alert threshold | `10%` |

**Usage:** Status bar shows `⬡ W:96% 5H:99%`. Hover for details. `Cmd+Shift+P → Kimi: Refresh`.

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
