```text
 ██╗  ██╗ ██╗ ███╗   ███╗ ██╗     ██████╗  ██████╗  ██████╗  ███████╗
 ██║ ██╔╝ ██║ ████╗ ████║ ██║    ██╔════╝ ██╔═══██╗ ██╔══██╗ ██╔════╝
 █████╔╝  ██║ ██╔████╔██║ ██║    ██║      ██║   ██║ ██║  ██║ █████╗
 ██╔═██╗  ██║ ██║╚██╔╝██║ ██║    ██║      ██║   ██║ ██║  ██║ ██╔══╝
 ██║  ██╗ ██║ ██║ ╚═╝ ██║ ██║    ╚██████╗ ╚██████╔╝ ██████╔╝ ███████╗
 ╚═╝  ╚═╝ ╚═╝ ╚═╝     ╚═╝ ╚═╝     ╚═════╝  ╚═════╝  ╚═════╝  ╚══════╝
```

> *Here am I sitting in a tin can*  
> *Far above the world*  
> *Planet Earth is blue*  
> *And there's nothing I can do*  
>  
> — **David Bowie**, *Space Oddity* (1969)

# Kimi Code Usage (Kimi 轨道遥测仪)

<p align="center">
  <a href="#"><img src="https://img.shields.io/visual-studio-marketplace/v/HainingYu.kimi-code-usage.svg" alt="Marketplace"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="#"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

<p align="center">
  <strong>Navigating your AI trajectory with orbital precision.</strong><br>
  <strong>以环月轨道的精度，感知你的 AI 资源余量。</strong>
</p>

---

<p align="center">
  <a href="https://ko-fi.com/golden_voyager"><img src="https://img.shields.io/badge/☕_Buy_me_a_coffee-Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Buy me a coffee" /></a>&nbsp;
  <a href="https://github.com/Golden0Voyager/kimi-code-usage"><img src="https://img.shields.io/badge/⭐_Star_on-GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Star on GitHub" /></a>
</p>

<p align="center">
  <em>If <strong>Kimi Code Usage</strong> keeps your flight on course, consider fueling the next trajectory.</em><br>
  <em>如果 <strong>Kimi Code Usage</strong> 让你的航线保持平稳，欢迎为下一段轨迹加杯燃料。</em>
  <br /><br />
  <a href="https://ko-fi.com/golden_voyager"><strong>☕ ko-fi.com/golden_voyager</strong></a>
</p>

---

### 🌑 Why Kimi Code Usage? | 为什么选择它？

In the vastness of the code universe, your creative flow shouldn't be pulled down by the unexpected gravity well of API quota limits. **Kimi Code Usage** acts as your orbital telemetry system. It brings transparency to your AI consumption, allowing you to focus on exploring the digital cosmos while maintaining full awareness of your life-support resources.

在广袤的代码宇宙中，你的灵感航线不应被突如其来的额度耗尽（引力井）所打断。**Kimi Code Usage** 如同你的专属轨道遥测仪，为你的 AI 消耗提供极简而透明的实时监控，让你在探索深空的专注中，对系统资源状况了然于胸。

---

### 🛰️ Telemetry Showcase | 遥测显示

```text
🌔 ▰▰▱  W:64% 5H:54%  > Walk
--------------------------------------------------
| Kimi API Telemetry Details                     |
| Weekly: 64% left  [Current Pace: -30% > Walk]  |
| 5 Hours: 54% left [Current Pace: -30% > Walk]  |
| Resets Today 16:22 (in 3d 17h)                 |
--------------------------------------------------
```

---

### ✨ Systems | 核心组件

- **Orbital HUD | 轨道级状态栏**
  A sleek indicator showing your remaining API telemetry at a glance.
  极致简洁的百分比显示，一眼看清飞船的剩余能量。
- **Pace Indicator | 曲率引擎指针**
  Real-time consumption velocity with 10 theme presets. Know whether you're burning fuel too fast or cruising efficiently.
  实时追踪 API 消耗速率，10 款主题预设（动物、赛车、星战…），洞悉燃料燃烧节奏：
  - 🌒 **Fast** — Burning faster than elapsed time. Red alert background. 消耗速度超过时间进度，触发红色警报背景。
  - 🌓 **Normal** — Right on schedule. Steady cruising. 消耗与时间进度同步，平稳巡航。
  - 🌔 **Slow** — Conserving fuel, well below pace. 节省燃料，远低于预期消耗。
- **Deep Space Insights | 深空数据探针**
  Hover to reveal fuel status, refuel times, and warp factor deviations.
  悬浮触发燃料主题数据面板，掌握长周期与短周期限额的每一处细节。
- **Thruster Controls | 推进器微调**
  - `Kimi: Refresh Usage` — Instant telemetry sync. (立即同步雷达数据)
  - `Kimi: Show Details` — Deep dive into stats with absolute reset times. (查看深空数据面板，含精确重置时间)
  - `Kimi: Show Usage History` — Open the flight recorder: usage over time, exhaustion prediction, and confidence. (打开黑匣子：用量历史、耗尽预测、置信度)
- **Flight Recorder | 黑匣子记录仪**
  Local JSONL snapshot every refresh (30-day retention). Inspect trends, forecast when you'll run out, and see the model confidence based on sample size.
  每次刷新写入本地 JSONL 快照（默认保留 30 天）。查看趋势曲线、预测耗尽时间，并根据样本量给出置信度。
- **Mission Alerts | 任务警报**
  Optional notifications when weekly / 5-hour quota drops below threshold, or when consumption pace goes hot. Deduped to avoid spam.
  当每周 / 5 小时配额跌破阈值、或消耗进入「快」档时弹通知；状态机去重避免刷屏。

---

### 🚀 Launch Sequence | 发射序列

1.  **Dock** the extension from the VS Code: Marketplace. (从商店安装扩展)
2.  **Calibrate** your API Key in Settings > `kimiCodeUsage.apiKey`, or via the `.env` module. (配置你的 API 密钥)
3.  **Liftoff!** Watch your quota manifest in the status bar. (点火起飞！在状态栏实时感知资源消耗)

---

### ⚙️ Navigation Specs | 导航配置

| Setting (配置节点) | Description (说明) | Default |
| :--- | :--- | :--- |
| `apiKey` | Your Kimi API secret / 核心密钥 | `KIMI_CODING_API_KEY` |
| `baseUrl` | API base URL / 接口基站 | `Kimi Coding V1` |
| `refreshIntervalMinutes` | Auto-sync minutes / 雷达刷新间隔 | `5` |
| `language` | Display language (Auto/English/Chinese/Japanese/French/German/Spanish/Korean/Russian/Portuguese/Italian) / 显示语言 | `Auto` |
| `weeklyLowThresholdPercent` | Weekly low quota threshold (%) / 每周低余量告警阈值 | `30` |
| `fiveHourLowThresholdPercent` | 5-hour low quota threshold (%) / 5小时低余量告警阈值 | `15` |
| `showPaceIndicator` | Show pace indicator / 显示速度指针 | `true` |
| `showPaceBar` | Show pace bar in status bar / 在状态栏显示速度进度条 | `true` |
| `statusBarAlignment` | Status bar alignment (Left/Right) / 状态栏对齐位置 | `Right` |
| `paceTheme` | Pace label theme preset (16 themes) / 主题预设 | `Simple` |
| `paceSensitivity` | Threshold sensitivity (Relaxed/Normal/Strict/Custom) / 灵敏度档位 | `Normal` |
| `paceThresholdFast` | Fast usage threshold / 用量过快阈值 | *(sensitivity preset)* |
| `paceThresholdSlow` | Slow usage threshold / 用量过慢阈值 | *(sensitivity preset)* |
| `paceLabels` | Custom pace labels (fast/normal/slow) / 自定义速度状态名称 | `{}` |
| `paceIcons` | Custom codicon names / 自定义状态图标名称 | `{}` |
| `redAlertCondition` | Which quota triggers red alert (Weekly/5 Hours/Either) / 红色告警触发条件 | `Either` |

---

### 📋 Changelog | 更新日志

**v0.1.9** — *History, Predictions & Engineering Overhaul*
- 📈 用量历史 Webview（`Kimi: Show Usage History`）：本地 JSONL 快照、Chart.js 折线图、默认保留 30 天
- 🔮 耗尽预测：线性回归估算每日消耗速率 + 预计耗尽日期，按样本量给出置信度（low/medium/high）
- 🔔 阈值/速度通知：余量跌破阈值或速度进入 fast 时弹信息提示，去重防骚扰
- 💾 API 响应缓存：默认 5 分钟 TTL，可通过 `kimiCodeUsage.apiCacheTtlSeconds` 调整
- 🛠️ 工程重构：`extension.ts` 从 987 行拆分为独立模块（`types` / `i18n` / `pace` / `api` / `config` / `statusBar` / `storage` / `predict` / `notifier` / `apiCache` / `historyPanel`），新增 109 个单元测试（Vitest）
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

---

<p align="center">
  <strong>See you on the dark side of the moon.</strong>
</p>
