# Changelog

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
