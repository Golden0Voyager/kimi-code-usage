# Kimi CLI 月度额度读取设计

## 目标

让 `uv run kimi-usage` 在不影响现有 Kimi 周额度与 5 小时窗口读取的前提下，展示已登录 Kimi 订阅页中的月度会员额度。

第一阶段只覆盖 CLI Rich 输出和 `--json` 输出；MCP、本地 Web 面板和 VS Code 扩展不在本次范围内。

## 数据源与边界

Kimi Code 的公开 `/usages` 接口目前只提供周额度和 5 小时窗口。月度额度由登录后的 `https://www.kimi.com/membership/subscription?tab=quota` 页面展示。

CLI 通过本机 Kimi WebBridge 复用浏览器登录态：先定位或打开订阅页，再读取其可访问结构中的额度文本。已验证页面会提供“总使用量”“N%”和“YYYY-MM-DD 后重置”等字段。网络捕获没有暴露可用请求，因此本功能不依赖未公开的 XHR/Fetch 端点。不会保存 Cookie、令牌、页面快照或任何账户标识。

该读取器是可选增强。WebBridge 未运行、扩展未连接、浏览器未登录、网页改版或请求失败时，命令仍成功返回现有周/5 小时数据，并为 Kimi 增加一条可恢复的月度读取错误。

## 架构

新增一个独立的 Kimi membership reader，负责：

1. 通过 WebBridge 守护进程检查浏览器桥接可用性。
2. 复用或打开 Kimi 订阅页，并读取其 WebBridge accessibility snapshot。
3. 从“用量进度”中的“总使用量”卡片解析已用百分比和月度重置时间，再标准化为现有 `ProviderUsage`。
4. 向 Kimi provider 返回该月度记录，或返回可读错误而不干扰 `/usages` 结果。

Kimi provider 继续以 `/usages` 为主来源。membership reader 只附加一条 `Monthly Credits`（中文环境下为“月度额度”）记录；不改变其他 provider 的接口或渲染逻辑。

## 命令行为

正常情况下，`uv run kimi-usage` 的 Kimi 分区按“月度、周、5 小时”顺序显示。`uv run kimi-usage --json` 的 `kimi` 数组新增同样结构的记录。

月度读取不可用时：

- 周与 5 小时记录照常输出；
- `errors.kimi` 或当前 Kimi 的附加错误信息明确说明原因与恢复方式，例如启动 WebBridge、打开已登录浏览器或重新登录 Kimi；
- 不伪造 0%、不将读取失败解释为额度耗尽。

## 测试

使用录制且脱敏的 WebBridge accessibility snapshot 作为 fixture，覆盖：

- 月度有效响应的字段解析与百分比计算；
- 已用/剩余两类响应形态；
- 缺失字段与未知响应形态；
- WebBridge 不可用或网络请求失败时，周/5 小时结果仍被保留；
- CLI JSON 输出包含月度记录。

单元测试不得依赖真实浏览器、Kimi 登录态或网络连接。

## 非目标

- 不提供或记录 Kimi Cookie、会话令牌与 API Key；
- 不绕过登录、验证码或访问控制；
- 不为 MCP、Web 面板和 VS Code 扩展新增月度数据；
- 不将未文档化的内部请求端点当作稳定公开 API。
