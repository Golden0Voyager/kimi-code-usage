# Changelog

## v0.2.1 — *Multi-Provider & Coverage Harness*

### 新增 / Added

- 🔌 **多 Provider 支持**：在 Kimi 之外新增 **OpenRouter**（`/auth/key` + `/credits`，美元额度）、
  **Anthropic**（`/api/oauth/usage`，5 小时 / 7 天窗口，仅接受 Claude Code OAuth 令牌）和
  **OpenAI**（组织用量 completions + costs，需要 Org Admin 密钥）三个适配器，
  忠实移植自 Python 版 `kimi-usage` CLI。
- 🆓 **OpenRouter 免费模型日限额行**：读取 `/auth/key` 的 `free_model_daily_requests`，
  显示 `Free Models  679/1000 free requests left today (resets at UTC 0)`
  （限额按 UTC 日重置、失败请求也计配额，见上游 CLI 同款功能）。
- 🗝️ **交互式密钥配置**：新命令 `Kimi Code Usage: Configure Providers`（`kimiCodeUsage.configureProviders`）
  — QuickPick 选择 provider，密码输入框粘贴密钥，可自定义 Base URL，写入用户设置后自动刷新。
- 🎛️ **主 Provider 制状态栏**：新增 `kimiCodeUsage.primaryProvider`（默认 `kimi`），
  状态栏只显示主 provider；其余启用的 provider 聚合到 tooltip 与详情面板（按 provider 分组）。
- ⚙️ 平铺配置项：`openrouterEnabled/ApiKey/BaseUrl`、`anthropicEnabled/ApiKey/BaseUrl`、
  `openaiEnabled/ApiKey/BaseUrl`、`kimiEnabled`，旧的 `apiKey`/`baseUrl` 语义不变。
- 🌍 新增文案（Credits、Rate Limit、Configure Providers 等 26 个 key）已翻译到全部 10 种语言。

### 变更 / Changed

- API 缓存键加入 provider 前缀，两个 provider 不会互相命中缓存。
- 各 provider 的 HTTP 错误统一携带 `HTTP <status>`，状态栏现在能对 401/429/5xx
  显示对应的锁 / 警告 / 服务器图标（此前一律显示通用错误）。
- User-Agent 版本号改为单一来源（`userAgent.ts`），此前 provider 请求永远报默认版本。

### 新增 / Added（覆盖率）

- 🧪 覆盖率门禁：CI 现在跑 `npm run test:coverage`，语句 / 分支 / 函数 / 行四项阈值均为 100%，
  覆盖率下降会直接让流水线失败。

### 说明 / Notes

- OpenRouter 的 `/activity` 图表不做：扩展的 History 面板已有自己的历史快照机制。
- OpenAI 普通 `sk-...` 项目密钥无法读取组织用量（API 限制），配置时会给出明确提示；
  ChatGPT Plus/Pro 订阅没有任何用量 API。

## v0.2.0 — *Extra Usage & Provider Rows*

### 新增 / Added

- 🧾 **Extra Usage（加油包）用量行**：Kimi 加油包钱包现在单独成行。钱包未启用时显示「未启用 / Not enabled」；
  启用但未报告金额时不虚构数字，整行省略。
- 📊 **并发数与总额度行**：读取线上 `/usages` 的 `parallel` 与 `totalQuota`。
- 🌍 上述新文案已翻译到全部 10 种语言。

### 修复 / Fixed

- 详情面板（QuickPick）此前对字面值行显示 `100% left`，现在如实显示该值。
- 钱包 / 余额字段若是数组，不再被误判为有效对象。
- 钱包处于启用状态但没有金额时，不再输出凭空捏造的行。

### 说明 / Notes

- 加油包、并发数、总额度等非窗口行只出现在悬浮提示与详情面板，
  不会挤进状态栏紧凑区。

## v0.1.9 — *History, Predictions & Engineering Overhaul*

- 📈 用量历史 Webview（`Kimi: Show Usage History`）：本地 JSONL 快照、Chart.js 折线图、默认保留 30 天
- 🔮 耗尽预测：线性回归估算每日消耗速率 + 预计耗尽日期，按样本量给出置信度（low/medium/high）
- 🔔 阈值/速度通知：余量跌破阈值或速度进入 fast 时弹信息提示，去重防骚扰
- 💾 API 响应缓存：默认 5 分钟 TTL，可通过 `kimiCodeUsage.apiCacheTtlSeconds` 调整
- 🛠️ 工程重构：`extension.ts` 从 987 行拆分为独立模块（`types` / `i18n` / `pace` / `api` / `config` /
  `statusBar` / `storage` / `predict` / `notifier` / `apiCache` / `historyPanel`），新增并提升至 **356** 个单元测试
  （Vitest 覆盖率达 **100.00%**）
- 🤖 CI：GitHub Actions 跑 typecheck / lint / test
- 🎨 引入 ESLint + Prettier

## v0.1.8 — *Support Link & Polish*

- 添加 Ko-fi 支持链接 / Added Ko-fi support link

## v0.1.7 — *Multilingual & UI Polish*

- 🌍 多语言支持（10 种语言：English / 中文 / 日本語 / Français / Deutsch / Español / 한국어 / Русский / Português / Italiano）
- 16 款速度指针主题预设（新增 F1 / Pink Floyd / Submarine / Airliner / Fighter / Firearms）
- 速度进度条独立开关 `showPaceBar`
- 状态栏位置控制 `statusBarAlignment`（Left / Right）
- 红色告警触发条件 `redAlertCondition`（Weekly / 5 Hours / Either）
- Settings 按钮移至 QuickPick 标题栏右侧
- Running 主题慢速标签统一为 Walk/漫步

## v0.1.6 — *Theme Engine & Threshold Control*

- 10 款速度指针主题预设（Default / Animals / Racing / Fish / Birds / Rocket / Running / Star Wars / Star Trek / Back To The Future）
- 4 档灵敏度联动阈值（Relaxed / Normal / Strict / Custom），档位切换自动同步阈值
- 自定义 Fast / Slow 分界阈值
- 状态栏用量边界 emoji（满额 🌕 / 耗尽 🌑）
- QuickPick 增加设置入口

## v0.1.5 — *Refined Telemetry*

- 品牌统一：Tom → Kimi
- 增强错误处理与状态栏提示

## v0.1.4 — *Pace Indicator*

- 实时消耗速率指针（Fast / Normal / Slow）
- 燃料主题悬浮提示与三格进度条
- 深空数据面板（QuickPick）

## v0.1.0 — *Liftoff*

- 状态栏余量监控与自动刷新
