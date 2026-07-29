# Usage Authentication and WebBridge Preflight Design

## Goal

Make interactive quota monitoring recover cleanly from two local dependency failures:

1. ChatGPT Plus usage should refresh an expired Codex access token and retry once.
2. Interactive Kimi usage should ask whether to start an installed but stopped Kimi WebBridge before loading the TUI.

The changes must not make WebBridge mandatory, must not prompt in non-interactive modes, and must not access real credentials or browsers in automated tests.

## Scope

### Included

- Codex 401 refresh, auth-file update, and one retry.
- A Kimi WebBridge lifecycle boundary for status detection and daemon startup.
- A preflight confirmation before entering `kimi-usage -i`.
- More precise monthly-usage errors for a stopped daemon, disconnected extension, and an unavailable Kimi subscription page.
- Unit and integration-style tests using fake auth files, fake subprocess results, and mocked HTTP/browser boundaries.
- README documentation for the interactive prompt and Codex recovery behavior.

### Excluded

- Using Playwright CLI as a production fallback.
- Starting WebBridge from plain, JSON, server, or MCP modes.
- Persisting the user's preflight choice.
- Automatically opening a browser or browser extension.
- Repeated or background token refresh loops.

## Architecture

### WebBridge lifecycle boundary

Add a focused module under `src/kimi_code_usage/providers/` that owns local WebBridge lifecycle operations:

- Resolve the fixed binary path `~/.kimi-webbridge/bin/kimi-webbridge`.
- Run `status` without a shell and parse its JSON response.
- Run `start` without a shell.
- Poll for a bounded period until the daemon reports `running: true`.

The module returns typed status information rather than user-facing TUI rows. The existing `kimi_membership.py` remains responsible for browser commands, subscription-page parsing, and translating WebBridge failures into monthly-usage messages.

### Interactive preflight

After configuration and `--provider` filtering, but before `_interactive_mode()` changes terminal mode:

1. Check that Kimi is enabled.
2. Check that Kimi is visible.
3. Check that the WebBridge binary is installed.
4. Read WebBridge status.
5. If the daemon is stopped, ask whether to start it.

The prompt is:

```text
Start Kimi WebBridge to fetch monthly credits? [Y/n]
```

The Chinese locale uses an equivalent Chinese prompt. The prompt appears on every qualifying interactive launch while the daemon is stopped. The answer is not saved.

If the user answers yes, start the daemon and wait only for the daemon to become ready. Do not block waiting for a browser extension because connecting it may require a human to open the browser. If the user answers no, enter the TUI normally; the monthly row detects and reports that the daemon is not running. No declined-choice state is passed into the provider or persisted.

The preflight is skipped when any of these conditions applies:

- The command is not interactive.
- Kimi is disabled.
- Kimi is hidden by `general.visibleProviders`.
- A `--provider` filter excludes Kimi.
- WebBridge is not installed.
- WebBridge is already running.

### Codex authentication retry

The Codex request sequence is:

1. Read `~/.codex/auth.json`.
2. Call `/backend-api/wham/usage` with the current access token and account ID.
3. On a non-401 response, preserve current behavior.
4. On 401 with a refresh token, refresh once through the OAuth token endpoint.
5. After a successful refresh, update the auth file while preserving unrelated top-level and token fields.
6. Retry `/wham/usage` once with the new access token.
7. If refresh fails or the retry returns 401, stop and instruct the user to run `codex login`.

There is no retry loop. A 401 without a refresh token immediately produces the login instruction.

## Error Handling

WebBridge failures are recoverable and affect only the Kimi monthly row:

| Condition | Monthly row behavior |
|---|---|
| Binary not installed | Explain that Kimi WebBridge is not installed |
| Daemon stopped and user declines | Explain that the WebBridge daemon is not running |
| Daemon start fails or times out | Show the bounded startup failure |
| Daemon running, extension disconnected | Ask the user to open the browser extension |
| Subscription page unavailable or logged out | Ask the user to log in and open the subscription page |
| Snapshot does not contain expected usage data | Report that monthly usage could not be found |

Weekly Kimi usage, the five-hour limit, and all other providers continue loading after every WebBridge failure.

Codex auth-file updates occur only after a successful OAuth refresh. The update writes a sibling temporary file and atomically replaces the auth file while retaining its existing permissions. Refresh or write failures must leave the existing auth file usable. The retry is capped at one request.

## Testing

Tests use dependency boundaries and temporary paths; they never use the real WebBridge binary, browser, network, or `~/.codex/auth.json`.

### WebBridge lifecycle

- Parses running and extension-connected status.
- Handles a missing binary, invalid status output, non-zero status, failed start, and startup timeout.
- Starts with an argument vector and never invokes a shell.

### Interactive preflight

- Prompts only for interactive, enabled, visible Kimi.
- Skips when Kimi is disabled, hidden, filtered out, WebBridge missing, or the daemon already runs.
- A yes answer invokes startup and still enters the TUI.
- A no answer does not invoke startup, does not write configuration, and still enters the TUI.
- Non-interactive, server, and MCP paths do not prompt.

### Kimi monthly usage

- Distinguishes a stopped daemon, disconnected extension, unavailable subscription page, and unparseable usage data.
- Preserves weekly and five-hour rows for all recoverable monthly failures.

### Codex

- First request succeeds without refreshing.
- First 401 refreshes, updates the fake auth file, and retries successfully.
- The auth update preserves unrelated fields.
- A missing refresh token, failed refresh, and second 401 each stop with a login instruction.
- Exactly one refresh and one retry are permitted.

### Final verification

Run:

```bash
rtk uv run pytest
rtk uv run pytest --cov=kimi_code_usage --cov-report=term-missing
rtk uv run ruff check .
```

The test suite must pass, coverage must meet the repository threshold, Ruff must be clean, and the worktree must contain no unexpected generated files.

## Documentation

Update both `README.md` and `README.zh.md` to explain:

- Interactive mode may ask to start an installed but stopped WebBridge.
- Declining affects only Kimi monthly credits.
- Browser extension connection and a logged-in Kimi session remain required.
- ChatGPT Plus usage automatically refreshes once on 401 and otherwise recommends `codex login`.
