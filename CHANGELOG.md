# Changelog

Notable changes to the Python package (`kimi-code-usage` on PyPI). The VS Code
extension has its own changelog: [`vscode-extension/CHANGELOG.md`](vscode-extension/CHANGELOG.md).

This file starts at 0.2.0; earlier releases are recorded by the `v0.1.0`–`v0.1.6`
git tags.

## [0.2.0] — 2026-10-20

### Added

- **Extra Usage row.** Kimi's booster wallet is now reported as its own row
  (`Extra Usage`, `加油包` in Chinese) instead of being invisible. A wallet that
  reports no usable amount produces no row rather than a made-up `¥0.00`.
- **Monthly quota over the CLI OAuth token.** Monthly credits are read through
  the Kimi Code CLI token, preferring that path and falling back to the
  WebBridge browser snapshot when one is available.
- Parsing of the live `/usages` payload shape, including its `booster_wallet`
  field.

### Changed

- **`fastmcp` floor raised from 0.1.0 to 4.1.1** (`mcp` 2). The MCP surface used
  here — `FastMCP(...)`, `@mcp.tool()`, `mcp.run()` — is unchanged, and the
  upgrade is covered by a real stdio smoke test (`initialize` → `tools/list` →
  `call_tool`). Projects that pin `mcp<2` in their own environment will need to
  relax that pin.

### Fixed

- Kimi: read the live `/usages` shape and count only emitted windows.
- Kimi: report OAuth monthly probe failures instead of dropping them silently.
- Kimi: only treat a wallet as live on an explicit signal, and stay silent when
  it is live but reports no amount.
- Codex: label each rate-limit window from its own `limit_window_seconds`.
- Claude: read the Claude Code OAuth token and utilization correctly.
- OpenRouter: handle `BaseException` from `asyncio.gather` and fix typing.
- Dependencies: upgraded the vulnerable locked packages; `aiohttp >= 3.14.3` is
  required for the patched parser.
