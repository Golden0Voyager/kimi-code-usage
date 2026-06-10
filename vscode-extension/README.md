```text
 ██╗  ██╗ ██╗ ███╗   ███╗ ██╗     ██████╗  ██████╗  ██████╗  ███████╗
 ██║ ██╔╝ ██║ ████╗ ████║ ██║    ██╔════╝ ██╔═══██╗ ██╔══██╗ ██╔════╝
 █████╔╝  ██║ ██╔████╔██║ ██║    ██║      ██║   ██║ ██║  ██║ █████╗
 ██╔═██╗  ██║ ██║╚██╔╝██║ ██║    ██║      ██║   ██║ ██║  ██║ ██╔══╝
 ██║  ██╗ ██║ ██║ ╚═╝ ██║ ██║    ╚██████╗ ╚██████╔╝ ██████╔╝ ███████╗
 ╚═╝  ╚═╝ ╚═╝ ╚═╝     ╚═╝ ╚═╝     ╚═════╝  ╚═════╝  ╚═════╝  ╚══════╝
```

> **English** · [中文](#中文)

<p align="center">
  <a href="#"><img src="https://img.shields.io/visual-studio-marketplace/v/HainingYu.kimi-code-usage.svg" alt="Marketplace"></a>
  <a href="#"><img src="https://img.shields.io/badge/statements-100%25-brightgreen" alt="Statements Coverage"></a>
  <a href="#"><img src="https://img.shields.io/badge/branches-100%25-brightgreen" alt="Branches Coverage"></a>
  <a href="#"><img src="https://img.shields.io/badge/functions-100%25-brightgreen" alt="Functions Coverage"></a>
  <a href="#"><img src="https://img.shields.io/badge/lines-100%25-brightgreen" alt="Lines Coverage"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="#"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

---

# English Version

## Kimi Code Usage

<p align="center">
  <strong>Navigating your AI trajectory with orbital precision.</strong>
</p>

<p align="center">
  <a href="https://ko-fi.com/golden_voyager"><img src="https://img.shields.io/badge/☕_Buy_me_a_coffee-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Buy me a coffee" /></a>&nbsp;
  <a href="https://github.com/Golden0Voyager/kimi-code-usage"><img src="https://img.shields.io/badge/⭐_Star_on-GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Star on GitHub" /></a>
</p>

<p align="center">
  <em>If <strong>Kimi Code Usage</strong> keeps your flight on course, consider fueling the next trajectory.</em>
  <br /><br />
  <a href="https://ko-fi.com/golden_voyager"><strong>☕ ko-fi.com/golden_voyager</strong></a>
</p>

### 🌑 Why Kimi Code Usage?

In the vastness of the code universe, your creative flow shouldn't be pulled down by the unexpected gravity well of API quota limits. **Kimi Code Usage** acts as your orbital telemetry system. It brings transparency to your AI consumption, allowing you to focus on exploring the digital cosmos while maintaining full awareness of your life-support resources.

### 🛰️ Telemetry Showcase

```text
🌔 ▰▰▱  W:64% 5H:54%  > Walk
--------------------------------------------------
| Kimi API Telemetry Details                     |
| Weekly: 64% left  [Current Pace: -30% > Walk]  |
| 5 Hours: 54% left [Current Pace: -30% > Walk]  |
| Resets Today 16:22 (in 3d 17h)                 |
--------------------------------------------------
```

### ✨ Key Features

* **Orbital HUD (Status Bar)**: A sleek indicator showing your remaining API telemetry at a glance.
* **Pace Indicator (Warp Factor)**: Real-time consumption velocity with 10 theme presets (Rocket, Star Wars, Racing, etc.). Know whether you're burning fuel too fast or cruising efficiently:
  * 🌒 **Fast** — Burning faster than elapsed time. Triggers red alert background.
  * 🌓 **Normal** — Right on schedule. Steady cruising.
  * 🌔 **Slow** — Conserving fuel, well below pace.
* **Deep Space Insights (QuickPick)**: Hover to reveal fuel status, refuel times, and warp factor deviations.
* **Thruster Controls (Commands)**:
  * `Kimi: Refresh Usage` — Instant telemetry sync.
  * `Kimi: Show Details` — Deep dive into stats with absolute reset times.
  * `Kimi: Show Usage History` — Open the flight recorder: usage over time, exhaustion prediction, and confidence.
* **Flight Recorder**: Local JSONL snapshot every refresh (30-day retention). Open WebView charts to inspect trends, forecast when you'll run out, and see the model confidence based on sample size.
* **Mission Alerts**: Optional notifications when weekly / 5-hour quota drops below threshold, or when consumption pace goes hot. Deduped to avoid spam.

### 🚀 Launch Sequence

1. **Dock** the extension from the VS Code Marketplace.
2. **Calibrate** your API Key in Settings > `kimiCodeUsage.apiKey`, or via the `.env` module.
3. **Liftoff!** Watch your quota manifest in the status bar.

### ⚙️ Navigation Specs (Settings)

| Setting (Property) | Description | Default |
| :--- | :--- | :--- |
| `kimiCodeUsage.apiKey` | Your Kimi API secret (or reads `KIMI_CODING_API_KEY`/`KIMI_API_KEY` env) | `""` |
| `kimiCodeUsage.baseUrl` | API base URL | `https://api.kimi.com/coding/v1` |
| `kimiCodeUsage.refreshIntervalMinutes` | Auto-sync minutes interval | `5` |
| `kimiCodeUsage.language` | Display language (Auto/English/Chinese/...) | `Auto` |
| `kimiCodeUsage.weeklyLowThresholdPercent` | Weekly low quota threshold (%) for warning | `30` |
| `kimiCodeUsage.fiveHourLowThresholdPercent` | 5-hour low quota threshold (%) for warning | `15` |
| `kimiCodeUsage.showPaceIndicator` | Show pace indicator (Fast/Normal/Slow) | `true` |
| `kimiCodeUsage.showPaceBar` | Show pace bar in status bar | `true` |
| `kimiCodeUsage.statusBarAlignment` | Status bar alignment (Left/Right) | `Right` |
| `kimiCodeUsage.paceTheme` | Pace label theme preset (Simple, Animals, etc.) | `Simple` |
| `kimiCodeUsage.paceSensitivity` | Threshold sensitivity (Relaxed/Normal/Strict/Custom) | `Normal` |
| `kimiCodeUsage.paceThresholdFast` | Fast usage threshold (for Custom sensitivity) | *(sensitivity preset)* |
| `kimiCodeUsage.paceThresholdSlow` | Slow usage threshold (for Custom sensitivity) | *(sensitivity preset)* |
| `kimiCodeUsage.paceLabels` | Custom pace labels by state (fast/normal/slow) | `{}` |
| `kimiCodeUsage.paceIcons` | Custom codicon names by pace state | `{}` |
| `kimiCodeUsage.redAlertCondition` | Which quota triggers red alert (Weekly/5 Hours/Either) | `Either` |
| `kimiCodeUsage.apiCacheTtlSeconds` | API response cache TTL in seconds | `300` |
| `kimiCodeUsage.historyRetentionDays` | Days to keep usage history snapshots | `30` |

---

# <a id="中文"></a>中文版

## Kimi Code Usage (Kimi 轨道遥测仪)

<p align="center">
  <strong>以环月轨道的精度，感知你的 AI 资源余量。</strong>
</p>

<p align="center">
  <a href="https://ko-fi.com/golden_voyager"><img src="https://img.shields.io/badge/☕_Buy_me_a_coffee-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Buy me a coffee" /></a>&nbsp;
  <a href="https://github.com/Golden0Voyager/kimi-code-usage"><img src="https://img.shields.io/badge/⭐_Star_on-GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Star on GitHub" /></a>
</p>

<p align="center">
  <em>如果 <strong>Kimi Code Usage</strong> 让你的航线保持平稳，欢迎为下一段轨迹加杯燃料。</em>
  <br /><br />
  <a href="https://ko-fi.com/golden_voyager"><strong>☕ ko-fi.com/golden_voyager</strong></a>
</p>

### 🌑 为什么选择 Kimi Code Usage？

在广袤的代码宇宙中，你的灵感心流不应被突如其来的配额耗尽（引力井）所打断。**Kimi Code Usage** 如同你的专属轨道遥测仪，为你的 AI 消耗提供极简而透明的实时监控，让你在探索数字深空的专注中，对系统资源状况了然于胸。

### 🛰️ 遥测面板显示

```text
🌔 ▰▰▱  W:64% 5H:54%  > Walk
--------------------------------------------------
| Kimi API Telemetry Details                     |
| Weekly: 64% left  [Current Pace: -30% > Walk]  |
| 5 Hours: 54% left [Current Pace: -30% > Walk]  |
| Resets Today 16:22 (in 3d 17h)                 |
--------------------------------------------------
```

### ✨ 核心功能

* **轨道级状态栏 (Orbital HUD)**：极致简洁的剩余百分比显示，一眼看清飞船的剩余能量。
* **曲率引擎指针 (Pace Indicator)**：实时追踪 API 消耗速率，10 款主题预设（动物、赛车、星战、火箭等），洞悉燃料燃烧节奏：
  * 🌒 **Fast** — 消耗速度快于时间进度。状态栏触发红色警报背景。
  * 🌓 **Normal** — 消耗与时间进度同步，平稳巡航。
  * 🌔 **Slow** — 节省燃料，远低于预期消耗。
* **深空数据探针 (Deep Space Insights)**：悬浮触发燃料主题数据面板，掌握长周期与短周期限额的每一处细节。
* **推进器微调 (Thruster Controls)**：
  * `Kimi: Refresh Usage` — 立即同步雷达数据。
  * `Kimi: Show Details` — 查看深空数据面板，含精确绝对重置时间。
  * `Kimi: Show Usage History` — 打开飞行记录仪：用量历史、耗尽预测、置信度。
* **黑匣子记录仪 (Flight Recorder)**：每次刷新写入本地 JSONL 快照（默认保留 30 天）。可通过 WebView 走势图查看消耗趋势、预测耗尽时间，并根据样本量计算预测置信度。
* **任务警报 (Mission Alerts)**：当每周 / 5 小时配额跌破阈值、或消耗进入「快」档时弹窗通知；带有状态机去重，避免消息刷屏骚扰。

### 🚀 发射步骤

1. 从 VS Code 插件市场搜索并安装 `Kimi Code Usage` 扩展。
2. 在插件设置中配置 `kimiCodeUsage.apiKey`，或者在项目环境变量里配置密钥。
3. **点火起飞！** 在状态栏实时感知你的资源消耗。

### ⚙️ 导航配置 (Settings)

| 设置项 (配置节点) | 说明 | 默认值 |
| :--- | :--- | :--- |
| `kimiCodeUsage.apiKey` | 你的 Kimi API 密钥（或读取 `KIMI_CODING_API_KEY`/`KIMI_API_KEY` 环境变量） | `""` |
| `kimiCodeUsage.baseUrl` | API 基础地址 | `https://api.kimi.com/coding/v1` |
| `kimiCodeUsage.refreshIntervalMinutes` | 自动雷达刷新间隔（分钟） | `5` |
| `kimiCodeUsage.language` | 显示语言（Auto/中文/English/日本語/等） | `Auto` |
| `kimiCodeUsage.weeklyLowThresholdPercent` | 每周低余量告警阈值 (%) | `30` |
| `kimiCodeUsage.fiveHourLowThresholdPercent` | 5小时低余量告警阈值 (%) | `15` |
| `kimiCodeUsage.showPaceIndicator` | 显示速度指针（快/正常/慢） | `true` |
| `kimiCodeUsage.showPaceBar` | 在状态栏显示速度进度条 | `true` |
| `kimiCodeUsage.statusBarAlignment` | 状态栏对齐位置 (Left/Right) | `Right` |
| `kimiCodeUsage.paceTheme` | 速度状态主题预设（Simple, Animals 等） | `Simple` |
| `kimiCodeUsage.paceSensitivity` | 阈值灵敏度（Relaxed/Normal/Strict/Custom） | `Normal` |
| `kimiCodeUsage.paceThresholdFast` | 快状态的自定义速度阈值 | *(由灵敏度预设)* |
| `kimiCodeUsage.paceThresholdSlow` | 慢状态的自定义速度阈值 | *(由灵敏度预设)* |
| `kimiCodeUsage.paceLabels` | 自定义各速度状态的显示文字 | `{}` |
| `kimiCodeUsage.paceIcons` | 自定义各速度状态的 Codicon 图标 | `{}` |
| `kimiCodeUsage.redAlertCondition` | 红色告警触发条件（Weekly / 5 Hours / Either） | `Either` |
| `kimiCodeUsage.apiCacheTtlSeconds` | API 响应数据本地缓存秒数 | `300` |
| `kimiCodeUsage.historyRetentionDays` | 历史记录本地快照保留天数 | `30` |

---

# Common Sections / 公共板块

### 📋 Changelog | 更新日志

**v0.1.9** — *History, Predictions & Engineering Overhaul*
- 📈 用量历史 Webview（`Kimi: Show Usage History`）：本地 JSONL 快照、Chart.js 折线图、默认保留 30 天
- 🔮 耗尽预测：线性回归估算每日消耗速率 + 预计耗尽日期，按样本量给出置信度（low/medium/high）
- 🔔 阈值/速度通知：余量跌破阈值或速度进入 fast 时弹信息提示，去重防骚扰
- 💾 API 响应缓存：默认 5 分钟 TTL，可通过 `kimiCodeUsage.apiCacheTtlSeconds` 调整
- 🛠️ 工程重构：`extension.ts` 从 987 行拆分为独立模块（`types` / `i18n` / `pace` / `api` / `config` / `statusBar` / `storage` / `predict` / `notifier` / `apiCache` / `historyPanel`），新增并提升至 **356** 个单元测试（Vitest 覆盖率达 **100.00%**）
- 🤖 CI：GitHub Actions 跑 typecheck / lint / test
- 🎨 引入 ESLint + Prettier

**v0.1.8** — *Support Link & Polish*
- 添加 Ko-fi 支持链接 / Added Ko-fi support link

**v0.1.7** — *Multilingual & UI Polish*
- 🌍 多语言支持（10 种语言：English / 中文 / 日本語 / Français / Deutsch / Español / 한국어 / Русский / Português / Italiano）
- 16 款速度指针主题预设（新增 F1 / Pink Floyd / Submarine / Airliner / Fighter / Firearms）
- 速度进度条独立开关 `showPaceBar`
- 状态栏位置控制 `statusBarAlignment`（Left / Right）
- 红色告警触发条件 `redAlertCondition`（Weekly / 5 Hours / Either）
- Settings 按钮移至 QuickPick 标题栏右侧
- Running 主题慢速标签统一为 Walk/漫步

**v0.1.6** — *Theme Engine & Threshold Control*
- 10 款速度指针主题预设（Default / Animals / Racing / Fish / Birds / Rocket / Running / Star Wars / Star Trek / Back To The Future）
- 4 档灵敏度联动阈值（Relaxed / Normal / Strict / Custom），档位切换自动同步阈值
- 自定义 Fast / Slow 分界阈值
- 状态栏用量边界 emoji（满额 🌕 / 耗尽 🌑）
- QuickPick 增加设置入口

**v0.1.5** — *Refined Telemetry*
- 品牌统一：Tom → Kimi
- 增强错误处理与状态栏提示

**v0.1.4** — *Pace Indicator*
- 实时消耗速率指针（Fast / Normal / Slow）
- 燃料主题悬浮提示与三格进度条
- 深空数据面板（QuickPick）

**v0.1.0** — *Liftoff*
- 状态栏余量监控与自动刷新

---

### 👨‍🚀 About the Commander | 关于指令长

Engineered with ❤️ by **Haining Yu**. This extension is a piece of digital architecture designed to bridge the gap between aesthetic curation and intuitive, AI-powered exploration.

由 **Haining Yu** 精心打磨。它不仅是一个开发工具，更是一件融合了美学策展与直觉化 AI 探索的数字航天舱组件。
