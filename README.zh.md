<p align="center">
  <img src="vscode-extension/assets/banner.png" width="100%" alt="Kimi Code Usage Banner">
</p>

> [English](README.md) · **中文**

# Kimi Code Usage：三端工具链

**以优雅的姿态，在终端、AI 助手与编辑器中感知你的 AI 额度。**

---

### 🌟 项目愿景

在"直觉编程"时代，资源的透明度是进入心流状态的前提。**Kimi Code Usage** 是一套精心打磨的工具链 — 三种形态，一个灵魂。

**统一前提：** 在环境变量或 `.env` 文件中设置 `KIMI_API_KEY`（[Kimi Coding Plan](https://api.kimi.com/coding/v1) API Key）。

---

### ⚡ CLI 终端报告器

> 在你的终端中渲染出带有工业美感的配额面板。

**安装与运行：**
```bash
pip install kimi-code-usage
kimi-usage              # 美观的 Rich 面板
kimi-usage --json       # 机器可读的 JSON
kimi-usage --plain      # 纯文本输出
```

或免安装直接运行：
```bash
uvx kimi-code-usage
```

---

### 🔍 MCP 智能体接口

> 让你的 AI 助手能够主动感知你的额度状态。

兼容 **Claude Code、Cursor、Windsurf、Hermes** 及所有支持 MCP 的 AI 工具。

**添加到 MCP 配置**（如 `~/.claude/settings.json`）：
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

> **注意：** MCP 服务器需要 `--from` 参数，因为 `kimi-mcp` 是独立于默认入口点的子命令。

配置后直接对 AI 说：*"帮我查一下 Kimi 用量。"*

---

### 💎 VS Code 编辑器插件

> 状态栏实时显示剩余百分比，颜色随额度变化而呼吸。

**安装：** 在 VS Code 插件市场搜索 `Kimi Code Usage`，或运行：
```bash
code --install-extension HainingYu.kimi-code-usage
```

**配置**（`设置 > kimiUsage`）：

| 设置项 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `apiKey` | API 密钥（或读取 `KIMI_API_KEY` 环境变量） | `""` |
| `refreshInterval` | 自动刷新间隔（分钟） | `5` |
| `warnPercent` | 黄色警告阈值 | `30%` |
| `criticalPercent` | 红色警报阈值 | `10%` |

**使用：** 状态栏显示 `⬡ W:96% 5H:99%`。悬停查看详情。`Cmd+Shift+P → Kimi: Refresh`。

---

## 📊 真实用量参考

> *¥199/月 Coding Plan 的实际用量是多少？对比按量付费能省多少？来自 5 个月的真实数据。*

**详细数据 → [`docs/kimi-code-usage.md`](docs/kimi-code-usage.md)**

### 1. 用户画像

| 项目 | 详情 |
|:---|:---|
| 方案 | 第三档 Allegretto（$31/月）→ **¥199/月** |
| 工作流 | Claude Code + kimi-for-coding，重度 vibe coding |
| 数据周期 | 2026-01 ~ 2026-05 全量记录（约 31.5 亿 tokens） |

### 2. 消耗结构

| 项目 | 5 个月累计 | 占比 |
|:---|:---|---:|
| 输入（Cache Miss） | ~1.54 亿 | 4.9% |
| 缓存创建 | ~0.89 亿 | 2.8% |
| 输出 | ~0.12 亿 | 0.4% |
| **缓存读取（Cache Hit）** | **~28.96 亿** | **91.9%** |
| **总计** | **~31.52 亿** | **100%** |

缓存命中率 **91.9%** 是 vibe coding 的典型特征——长会话中每轮携带完整历史，仅最新一轮为 cache miss。

### 3. 实际月消耗

基于近一周连续采样（3 天占周额度 30%）推得：

| 指标 | 数值 |
|:---|:---:|
| 周消耗 | ~3.2 亿 tokens |
| **月消耗** | **≈ 13.7 ~ 15 亿 tokens** |
| 方案费用 | ¥199/月 |
| **折算有效费率** | **≈ ¥0.14 / 百万 tokens** |

### 4. 费用对比

按 **Kimi K2.6 标准 API 定价**（输入 ¥6.50 / 缓存 ¥1.10 / 输出 ¥27.00 每百万 tokens）计算等量消耗的费用：

| 场景 | 月费用 | 倍数 |
|:---|:---:|:---:|
| **Kimi Coding Plan（¥199）** | **¥199** | **1×** |
| 按量付费（K2.6 标准价） | **≈ ¥2,420** | **12.2×** |

| 按量付费明细 | 月用量 | 单价 | 费用 |
|:---|---:|:---:|---:|
| 输入（Cache Miss） | 7,350 万 | ¥6.50/百万 | ¥478 |
| 缓存读取（Cache Hit） | 13.79 亿 | ¥1.10/百万 | ¥1,516 |
| 输出 | 555 万 | ¥27.00/百万 | ¥150 |
| 缓存创建 | 4,250 万 | ¥6.50/百万 | ¥276 |
| **合计** | **15 亿** | | **¥2,420** |

### 5. 结论

> **Coding Plan 每月为重度用户节省约 ¥2,221（约 92%）。** 核心原因：缓存读取占总 tokens 92%，而 Plan 将其和输入都包在订阅费内；按量付费下这部分占账单 63%。

### ⚠️ 免责声明

> 本分析基于单用户 2026-01~05 期间的实际用量数据（`ccusage` 采集），各项比例和费用估算**仅供参考**。实际结果因会话模式、模型选择、缓存策略和 API 定价变化而异。定价截至 2026-05-24，引用自 [platform.kimi.com](https://platform.kimi.com)。

---

### 🎨 关于策展人

由 **Haining Yu** 精心打磨。作为一名艺术策展人与 Vibecoder，我将代码视作展览，力求在审美策展与直觉化 AI 编程之间寻找完美的平衡。

---

<p align="center">
  <strong>Enjoy the flow. Stay in the vibe.</strong>
</p>
