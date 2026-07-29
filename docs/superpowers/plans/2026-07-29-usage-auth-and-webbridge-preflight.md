# Usage Authentication and WebBridge Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive Kimi WebBridge startup prompt with precise recoverable diagnostics, and make ChatGPT Plus usage refresh an expired Codex token and retry once.

**Architecture:** Introduce a focused synchronous WebBridge lifecycle module that wraps the installed local binary and exposes typed status/start operations. Keep terminal prompting in `main.py`, browser-page parsing in `kimi_membership.py`, and Codex OAuth/request handling in `codex.py`; every external boundary is injectable or patchable in tests.

**Tech Stack:** Python 3.10+, asyncio, subprocess, Rich, aiohttp, cloudscraper, pytest, pytest-asyncio.

## Global Constraints

- Prompt only for `kimi-usage -i` when Kimi is enabled and visible and the installed WebBridge daemon is stopped.
- Ask on every qualifying launch; never persist the answer.
- Never prompt or auto-start in plain, JSON, server, or MCP modes.
- Do not open a browser or wait for the browser extension.
- Every WebBridge failure affects only the Kimi monthly row.
- Refresh Codex authentication at most once and retry usage at most once.
- Never access real auth files, browsers, daemons, or networks in automated tests.
- Preserve unrelated auth JSON fields and existing file permissions during atomic replacement.

---

## File Structure

- Create `src/kimi_code_usage/providers/webbridge.py`: installed binary path, typed status, startup, bounded polling, and process-local startup diagnostic.
- Create `tests/test_provider_webbridge.py`: lifecycle boundary tests with fake paths and mocked subprocess/time.
- Modify `src/kimi_code_usage/providers/kimi_membership.py`: translate command failures using lifecycle status.
- Modify `tests/test_provider_kimi_membership.py`: precise recoverable-error coverage.
- Modify `src/kimi_code_usage/main.py`: interactive-only preflight prompt before terminal cbreak mode.
- Modify `tests/test_main.py`: prompt eligibility and yes/no behavior.
- Modify `src/kimi_code_usage/providers/codex.py`: atomic auth update plus refresh-and-retry request flow.
- Modify `tests/test_provider_codex.py`: refresh success/failure/retry cap and auth preservation.
- Modify `README.md`: English behavior documentation.
- Modify `README.zh.md`: Chinese behavior documentation.

### Task 1: WebBridge Lifecycle Boundary

**Files:**
- Create: `src/kimi_code_usage/providers/webbridge.py`
- Create: `tests/test_provider_webbridge.py`

**Interfaces:**
- Produces: `WebBridgeStatus(installed: bool, running: bool, extension_connected: bool, detail: str | None = None)`.
- Produces: `get_webbridge_status() -> WebBridgeStatus`.
- Produces: `start_webbridge(*, timeout_seconds: float = 3.0, poll_interval: float = 0.1) -> WebBridgeStatus`.
- Produces: `last_webbridge_start_error() -> str | None`.
- Produces: `WebBridgeLifecycleError`.

- [ ] **Step 1: Write failing status tests**

Create `tests/test_provider_webbridge.py` with fake binary paths and mocked `subprocess.run`:

```python
import json
import subprocess
from unittest.mock import patch

import pytest

from kimi_code_usage.providers.webbridge import (
    WebBridgeStatus,
    get_webbridge_status,
)


def _completed(stdout: str, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(["kimi-webbridge"], returncode, stdout, stderr)


def test_status_reports_missing_binary(tmp_path):
    with patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", tmp_path / "missing"):
        assert get_webbridge_status() == WebBridgeStatus(
            installed=False,
            running=False,
            extension_connected=False,
        )


def test_status_parses_daemon_and_extension(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    payload = {"running": True, "extension_connected": True}
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed(json.dumps(payload)),
        ) as run,
    ):
        status = get_webbridge_status()
    assert status == WebBridgeStatus(True, True, True)
    assert run.call_args.args[0] == [str(binary), "status"]
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize(
    ("completed", "detail"),
    [
        (_completed("", returncode=1, stderr="status failed"), "status failed"),
        (_completed("not-json"), "invalid status response"),
    ],
)
def test_status_returns_diagnostic_for_command_failure(tmp_path, completed, detail):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch("kimi_code_usage.providers.webbridge.subprocess.run", return_value=completed),
    ):
        status = get_webbridge_status()
    assert status.installed is True
    assert status.running is False
    assert detail in (status.detail or "")
```

- [ ] **Step 2: Run status tests and verify RED**

Run:

```bash
rtk uv run pytest tests/test_provider_webbridge.py -v
```

Expected: collection fails because `kimi_code_usage.providers.webbridge` does not exist.

- [ ] **Step 3: Implement typed status**

Create `src/kimi_code_usage/providers/webbridge.py`:

```python
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

WEBBRIDGE_BIN = Path.home() / ".kimi-webbridge" / "bin" / "kimi-webbridge"
_LAST_START_ERROR: str | None = None


class WebBridgeLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebBridgeStatus:
    installed: bool
    running: bool
    extension_connected: bool
    detail: str | None = None


def get_webbridge_status() -> WebBridgeStatus:
    if not WEBBRIDGE_BIN.exists():
        return WebBridgeStatus(False, False, False)
    try:
        result = subprocess.run(
            [str(WEBBRIDGE_BIN), "status"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return WebBridgeStatus(True, False, False, str(exc))
    if result.returncode != 0:
        return WebBridgeStatus(
            True,
            False,
            False,
            result.stderr.strip() or f"status exited {result.returncode}",
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return WebBridgeStatus(True, False, False, "invalid status response")
    return WebBridgeStatus(
        installed=True,
        running=bool(payload.get("running")),
        extension_connected=bool(payload.get("extension_connected")),
    )


def last_webbridge_start_error() -> str | None:
    return _LAST_START_ERROR
```

- [ ] **Step 4: Run status tests and verify GREEN**

Run:

```bash
rtk uv run pytest tests/test_provider_webbridge.py -v
```

Expected: status tests pass; startup imports may still be absent until the next test is added.

- [ ] **Step 5: Write failing startup tests**

Append:

```python
from kimi_code_usage.providers.webbridge import (
    WebBridgeLifecycleError,
    last_webbridge_start_error,
    start_webbridge,
)


def test_start_runs_binary_and_stops_after_daemon_is_ready(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    stopped = WebBridgeStatus(True, False, False)
    running = WebBridgeStatus(True, True, False)
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("started"),
        ) as run,
        patch(
            "kimi_code_usage.providers.webbridge.get_webbridge_status",
            side_effect=[stopped, running],
        ),
        patch("kimi_code_usage.providers.webbridge.time.sleep"),
    ):
        assert start_webbridge(timeout_seconds=1, poll_interval=0.01) == running
    assert run.call_args.args[0] == [str(binary), "start"]
    assert run.call_args.kwargs["shell"] is False


def test_start_failure_is_exposed_as_process_local_diagnostic(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("", returncode=1, stderr="cannot bind"),
        ),
    ):
        with pytest.raises(WebBridgeLifecycleError, match="cannot bind"):
            start_webbridge()
    assert last_webbridge_start_error() == "cannot bind"


def test_start_times_out_when_daemon_never_runs(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    stopped = WebBridgeStatus(True, False, False)
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("started"),
        ),
        patch(
            "kimi_code_usage.providers.webbridge.get_webbridge_status",
            return_value=stopped,
        ),
        patch(
            "kimi_code_usage.providers.webbridge.time.monotonic",
            side_effect=[0.0, 0.0, 4.0],
        ),
        patch("kimi_code_usage.providers.webbridge.time.sleep"),
    ):
        with pytest.raises(WebBridgeLifecycleError, match="did not become ready"):
            start_webbridge(timeout_seconds=3)
```

- [ ] **Step 6: Run startup tests and verify RED**

Run:

```bash
rtk uv run pytest tests/test_provider_webbridge.py -v
```

Expected: startup tests fail because `start_webbridge` is not implemented.

- [ ] **Step 7: Implement bounded startup**

Append to `webbridge.py`:

```python
def _set_start_error(message: str | None) -> None:
    global _LAST_START_ERROR
    _LAST_START_ERROR = message


def start_webbridge(
    *, timeout_seconds: float = 3.0, poll_interval: float = 0.1
) -> WebBridgeStatus:
    if not WEBBRIDGE_BIN.exists():
        message = "Kimi WebBridge is not installed"
        _set_start_error(message)
        raise WebBridgeLifecycleError(message)
    _set_start_error(None)
    try:
        result = subprocess.run(
            [str(WEBBRIDGE_BIN), "start"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _set_start_error(str(exc))
        raise WebBridgeLifecycleError(str(exc)) from exc
    if result.returncode != 0:
        message = result.stderr.strip() or f"start exited {result.returncode}"
        _set_start_error(message)
        raise WebBridgeLifecycleError(message)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = get_webbridge_status()
        if status.running:
            return status
        time.sleep(poll_interval)
    message = "Kimi WebBridge did not become ready before timeout"
    _set_start_error(message)
    raise WebBridgeLifecycleError(message)
```

- [ ] **Step 8: Run lifecycle tests and commit**

Run:

```bash
rtk uv run pytest tests/test_provider_webbridge.py -v
rtk uv run ruff check src/kimi_code_usage/providers/webbridge.py tests/test_provider_webbridge.py
rtk git add src/kimi_code_usage/providers/webbridge.py
rtk git add tests/test_provider_webbridge.py
rtk git commit -m "feat: add WebBridge lifecycle boundary"
```

Expected: all lifecycle tests and Ruff pass.

### Task 2: Precise Kimi Monthly Diagnostics

**Files:**
- Modify: `src/kimi_code_usage/providers/kimi_membership.py`
- Modify: `tests/test_provider_kimi_membership.py`

**Interfaces:**
- Consumes: `get_webbridge_status()` and `last_webbridge_start_error()`.
- Produces: `_webbridge_unavailable_message() -> str`.
- Preserves: `fetch_monthly_usage_from_webbridge(*, lang_zh: bool) -> ProviderUsage`.

- [ ] **Step 1: Write failing diagnostic tests**

Add tests that patch lifecycle status:

```python
from kimi_code_usage.providers.webbridge import WebBridgeStatus


@pytest.mark.parametrize(
    ("status", "start_error", "expected"),
    [
        (WebBridgeStatus(False, False, False), None, "not installed"),
        (WebBridgeStatus(True, False, False), None, "daemon is not running"),
        (WebBridgeStatus(True, False, False), "cannot bind", "cannot bind"),
        (WebBridgeStatus(True, True, False), None, "browser extension is not connected"),
    ],
)
def test_webbridge_unavailable_message_distinguishes_local_states(
    status, start_error, expected
):
    with (
        patch(
            "kimi_code_usage.providers.kimi_membership.get_webbridge_status",
            return_value=status,
        ),
        patch(
            "kimi_code_usage.providers.kimi_membership.last_webbridge_start_error",
            return_value=start_error,
        ),
    ):
        assert expected in _webbridge_unavailable_message()
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
rtk uv run pytest tests/test_provider_kimi_membership.py -v
```

Expected: failure because `_webbridge_unavailable_message` is absent.

- [ ] **Step 3: Implement diagnostic translation**

Import lifecycle helpers and add:

```python
def _webbridge_unavailable_message() -> str:
    status = get_webbridge_status()
    if not status.installed:
        return "Kimi WebBridge is not installed."
    start_error = last_webbridge_start_error()
    if not status.running:
        if start_error:
            return f"Kimi WebBridge failed to start: {start_error}"
        return "Kimi WebBridge daemon is not running."
    if not status.extension_connected:
        return "Kimi WebBridge browser extension is not connected; open the browser extension."
    return status.detail or "Kimi WebBridge command failed."
```

Replace the three generic unavailable strings in `_bridge_command` with `_webbridge_unavailable_message()`. Preserve exception chaining for connection and timeout failures.

- [ ] **Step 4: Add and verify page-state tests**

Keep the existing “monthly usage not found” test and add assertions that this message remains distinct from lifecycle failures:

```python
@pytest.mark.asyncio
async def test_fetch_monthly_usage_explains_logged_out_or_missing_page_data():
    responses = [
        {"ok": True, "data": {"success": True}},
        *[
            {"ok": True, "data": {"tree": [[{"name": "Sign in"}]]}}
            for _ in range(3)
        ],
    ]
    with patch(
        "kimi_code_usage.providers.kimi_membership._bridge_command",
        new=AsyncMock(side_effect=responses),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="log in"):
            await fetch_monthly_usage_from_webbridge(lang_zh=False)
```

Run:

```bash
rtk uv run pytest tests/test_provider_kimi_membership.py tests/test_provider_kimi.py -v
rtk uv run ruff check src/kimi_code_usage/providers/kimi_membership.py tests/test_provider_kimi_membership.py
```

Expected: all Kimi tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/kimi_code_usage/providers/kimi_membership.py
rtk git add tests/test_provider_kimi_membership.py
rtk git commit -m "fix: clarify Kimi monthly usage failures"
```

### Task 3: Interactive WebBridge Preflight

**Files:**
- Modify: `src/kimi_code_usage/main.py`
- Modify: `tests/test_main.py`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- Consumes: `get_webbridge_status()` and `start_webbridge()`.
- Produces: `_should_offer_webbridge_start(config: AppConfig) -> bool`.
- Produces: `_preflight_webbridge(config: AppConfig, *, lang_zh: bool) -> None`.

- [ ] **Step 1: Write failing prompt-eligibility tests**

Add a helper config with enabled Kimi, then cover disabled/hidden states:

```python
def test_should_offer_webbridge_start_requires_enabled_visible_kimi():
    cfg = AppConfig(
        providers={"kimi": ProviderConfig(api_key="k", enabled=True)},
        provider_order=["kimi"],
        visible_providers=["kimi"],
    )
    assert _should_offer_webbridge_start(cfg) is True
    cfg.visible_providers = []
    assert _should_offer_webbridge_start(cfg) is False
    cfg.visible_providers = ["kimi"]
    cfg.providers["kimi"].enabled = False
    assert _should_offer_webbridge_start(cfg) is False
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
rtk uv run pytest tests/test_main.py::test_should_offer_webbridge_start_requires_enabled_visible_kimi -v
```

Expected: failure because `_should_offer_webbridge_start` is absent.

- [ ] **Step 3: Implement eligibility**

In `main.py`:

```python
def _should_offer_webbridge_start(config: AppConfig) -> bool:
    kimi = config.providers.get("kimi")
    if not kimi or not kimi.enabled or not kimi.api_key:
        return False
    return config.visible_providers is None or "kimi" in config.visible_providers
```

- [ ] **Step 4: Write failing preflight tests**

Cover stopped/yes, stopped/no, already running, and missing binary:

```python
@pytest.mark.parametrize("answer", [True, False])
def test_preflight_prompts_each_time_daemon_is_stopped(answer):
    cfg = _enabled_visible_kimi_config()
    stopped = WebBridgeStatus(True, False, False)
    with (
        patch("kimi_code_usage.main.get_webbridge_status", return_value=stopped),
        patch("kimi_code_usage.main.Confirm.ask", return_value=answer) as ask,
        patch("kimi_code_usage.main.start_webbridge") as start,
    ):
        _preflight_webbridge(cfg, lang_zh=False)
    ask.assert_called_once()
    assert start.called is answer


@pytest.mark.parametrize(
    "status",
    [
        WebBridgeStatus(False, False, False),
        WebBridgeStatus(True, True, False),
    ],
)
def test_preflight_skips_missing_or_running_webbridge(status):
    cfg = _enabled_visible_kimi_config()
    with (
        patch("kimi_code_usage.main.get_webbridge_status", return_value=status),
        patch("kimi_code_usage.main.Confirm.ask") as ask,
    ):
        _preflight_webbridge(cfg, lang_zh=False)
    ask.assert_not_called()
```

- [ ] **Step 5: Run and verify RED**

Run:

```bash
rtk uv run pytest tests/test_main.py -k "webbridge_start or preflight_webbridge" -v
```

Expected: failure because `_preflight_webbridge` is absent.

- [ ] **Step 6: Implement terminal preflight**

Import `Confirm`, lifecycle operations, and add:

```python
def _preflight_webbridge(config: AppConfig, *, lang_zh: bool) -> None:
    if not _should_offer_webbridge_start(config):
        return
    status = get_webbridge_status()
    if not status.installed or status.running or status.detail:
        return
    prompt = (
        "是否启动 Kimi WebBridge 以获取月度额度？"
        if lang_zh
        else "Start Kimi WebBridge to fetch monthly credits?"
    )
    if Confirm.ask(prompt, default=True):
        try:
            start_webbridge()
        except WebBridgeLifecycleError as exc:
            Console().print(f"[yellow]{exc}[/yellow]")
```

Call `_preflight_webbridge` only in the `args.interactive` branch, immediately before `_interactive_mode`. Derive language with the same precedence as `_interactive_mode`:

```python
lang_zh = config.language == "zh" or (config.language not in {"zh", "en"} and IS_ZH)
_preflight_webbridge(config, lang_zh=lang_zh)
await _interactive_mode(config, theme_name, config_path=str(resolver.config_path))
```

- [ ] **Step 7: Verify routing and non-interactive isolation**

Extend `test_main_interactive_flag` to assert the preflight occurs before `_interactive_mode`. Add a plain-mode test patching `_preflight_webbridge` and asserting it is not called.

Run:

```bash
rtk uv run pytest tests/test_main.py -k "interactive or webbridge or preflight" -v
```

Expected: all selected tests pass.

- [ ] **Step 8: Update documentation**

In both README files, document that interactive mode asks each time an installed daemon is stopped, declining affects only monthly credits, and browser extension/login remain required.

- [ ] **Step 9: Run focused checks and commit**

```bash
rtk uv run pytest tests/test_main.py tests/test_provider_kimi_membership.py tests/test_provider_kimi.py -v
rtk uv run ruff check src/kimi_code_usage/main.py tests/test_main.py
rtk git add src/kimi_code_usage/main.py
rtk git add tests/test_main.py
rtk git add README.md
rtk git add README.zh.md
rtk git commit -m "feat: prompt to start Kimi WebBridge"
```

### Task 4: Codex 401 Refresh and Retry

**Files:**
- Modify: `src/kimi_code_usage/providers/codex.py`
- Modify: `tests/test_provider_codex.py`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- Preserves: `fetch_codex_usage(api_key: str, base_url: str, management_key: str | None = None) -> list[ProviderUsage]`.
- Changes: `_write_auth(auth_data: dict[str, Any]) -> None` to use atomic replacement and preserve permissions.
- Adds: `_fetch_usage_response(usage_url: str, access_token: str, account_id: str) -> tuple[int, str, dict[str, Any] | None]`.

- [ ] **Step 1: Write failing atomic-auth test**

Use a temporary auth path:

```python
import stat

from kimi_code_usage.providers.codex import _write_auth


def test_write_auth_preserves_fields_and_permissions(tmp_path):
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "other": {"keep": True},
                "tokens": {
                    "access_token": "old",
                    "refresh_token": "old-refresh",
                    "account_id": "acct",
                    "id_token": "keep-id",
                },
            }
        )
    )
    auth_path.chmod(0o600)
    with (
        patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path),
        patch(
            "kimi_code_usage.providers.codex.os.replace",
            wraps=os.replace,
        ) as replace,
    ):
        _write_auth({"access_token": "new", "refresh_token": "new-refresh"})
    saved = json.loads(auth_path.read_text())
    replace.assert_called_once()
    assert saved["other"] == {"keep": True}
    assert saved["tokens"]["id_token"] == "keep-id"
    assert saved["tokens"]["access_token"] == "new"
    assert stat.S_IMODE(auth_path.stat().st_mode) == 0o600
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
rtk uv run pytest tests/test_provider_codex.py::test_write_auth_preserves_fields_and_permissions -v
```

Expected: failure because the current direct writer never calls `os.replace`.

- [ ] **Step 3: Implement atomic auth replacement**

Replace direct writing with:

```python
mode = CODEX_AUTH_PATH.stat().st_mode if CODEX_AUTH_PATH.exists() else None
temp_path = CODEX_AUTH_PATH.with_name(f".{CODEX_AUTH_PATH.name}.tmp")
try:
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    if mode is not None:
        os.chmod(temp_path, mode)
    os.replace(temp_path, CODEX_AUTH_PATH)
except OSError as exc:
    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        pass
    raise RuntimeError(f"Failed to write Codex auth file: {exc}") from exc
```

Add a test patching `os.replace` to raise and assert the original file remains unchanged.

- [ ] **Step 4: Write failing 401 refresh tests**

Use `make_mock_scraper` with sequential GET responses and mocked token refresh:

```python
@pytest.mark.asyncio
async def test_fetch_401_refreshes_persists_and_retries_once(tmp_path):
    auth_path = make_auth_file(tmp_path)
    unauthorized = MagicMock(status_code=401, text="Unauthorized")
    success = MagicMock(status_code=200)
    success.json.return_value = {"plan_type": "plus"}
    scraper = MagicMock()
    scraper.get.side_effect = [unauthorized, success]
    with (
        patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path),
        patch("cloudscraper.create_scraper", return_value=scraper),
        patch(
            "kimi_code_usage.providers.codex._refresh_access_token",
            new=AsyncMock(
                return_value={
                    "access_token": "fresh-access",
                    "refresh_token": "fresh-refresh",
                }
            ),
        ) as refresh,
    ):
        rows = await fetch_codex_usage("enabled", "https://chatgpt.com/backend-api")
    assert rows[0].text_value == "ChatGPT Plus"
    refresh.assert_awaited_once_with("test-refresh-token")
    assert scraper.get.call_count == 2
    assert scraper.get.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer fresh-access"
    saved = json.loads(auth_path.read_text())
    assert saved["tokens"]["access_token"] == "fresh-access"


@pytest.mark.asyncio
async def test_fetch_second_401_stops_after_one_retry(tmp_path):
    auth_path = make_auth_file(tmp_path)
    unauthorized = MagicMock(status_code=401, text="Unauthorized")
    scraper = MagicMock()
    scraper.get.side_effect = [unauthorized, unauthorized]
    with (
        patch("kimi_code_usage.providers.codex.CODEX_AUTH_PATH", auth_path),
        patch("cloudscraper.create_scraper", return_value=scraper),
        patch(
            "kimi_code_usage.providers.codex._refresh_access_token",
            new=AsyncMock(
                return_value={
                    "access_token": "fresh-access",
                    "refresh_token": "fresh-refresh",
                }
            ),
        ) as refresh,
    ):
        with pytest.raises(RuntimeError, match="codex login"):
            await fetch_codex_usage("enabled", "https://chatgpt.com/backend-api")
    assert refresh.await_count == 1
    assert scraper.get.call_count == 2
```

Add separate tests for no refresh token and refresh endpoint failure. Assert both perform one usage request and do not modify the fake auth file.

- [ ] **Step 5: Run and verify RED**

Run:

```bash
rtk uv run pytest tests/test_provider_codex.py -k "401 or refreshes_persists or second_401" -v
```

Expected: the success case fails with the current immediate 401 exception.

- [ ] **Step 6: Implement one refresh and one retry**

Extract synchronous request construction:

```python
def _fetch_usage_response(
    usage_url: str, access_token: str, account_id: str
) -> tuple[int, str, dict[str, Any] | None]:
    scraper = cloudscraper.create_scraper()
    response = scraper.get(
        usage_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "ChatGPT-Account-Id": account_id,
        },
        timeout=15,
    )
    data = response.json() if response.status_code == 200 else None
    return response.status_code, response.text, data
```

In `fetch_codex_usage`:

```python
status, body, data = await asyncio.to_thread(
    _fetch_usage_response, usage_url, access_token, account_id
)
if status == 401:
    if not refresh_token:
        raise RuntimeError(
            "Codex API returned 401 and no refresh token is available. "
            "Run `codex login`."
        )
    refreshed = await _refresh_access_token(refresh_token)
    _write_auth(refreshed)
    status, body, data = await asyncio.to_thread(
        _fetch_usage_response,
        usage_url,
        refreshed["access_token"],
        account_id,
    )
if status == 401:
    raise RuntimeError(
        "Codex API still returned 401 after one token refresh. Run `codex login`."
    )
if status != 200:
    raise RuntimeError(f"Codex API Error (HTTP {status}): {body[:500]}")
assert data is not None
return _parse_usage_response(data)
```

Wrap refresh failure once so it retains the OAuth detail and adds the recovery action:

```python
try:
    refreshed = await _refresh_access_token(refresh_token)
except RuntimeError as exc:
    raise RuntimeError(f"{exc} Run `codex login`.") from exc
```

- [ ] **Step 7: Run focused Codex tests**

Run:

```bash
rtk uv run pytest tests/test_provider_codex.py -v
rtk uv run ruff check src/kimi_code_usage/providers/codex.py tests/test_provider_codex.py
```

Expected: all Codex tests and Ruff pass.

- [ ] **Step 8: Update documentation and commit**

Document one automatic refresh/retry and the remaining `codex login` fallback in both READMEs.

```bash
rtk git add src/kimi_code_usage/providers/codex.py
rtk git add tests/test_provider_codex.py
rtk git add README.md
rtk git add README.zh.md
rtk git commit -m "fix: refresh Codex token after unauthorized response"
```

### Task 5: Full Verification and Side-Effect Audit

**Files:**
- Verify only; modify a file only if a failing check identifies an in-scope defect.

**Interfaces:**
- Consumes all prior task outputs.
- Produces a clean, tested feature branch ready for review.

- [ ] **Step 1: Run focused combined regression**

```bash
rtk uv run pytest \
  tests/test_provider_webbridge.py \
  tests/test_provider_kimi_membership.py \
  tests/test_provider_kimi.py \
  tests/test_provider_codex.py \
  tests/test_main.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run complete suite**

```bash
rtk uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run coverage**

```bash
rtk uv run pytest --cov=kimi_code_usage --cov-report=term-missing
```

Expected: all tests pass and total coverage meets or exceeds the configured 85% threshold.

- [ ] **Step 4: Run static checks**

```bash
rtk uv run ruff check .
rtk uv run mypy
```

Expected: Ruff and mypy pass without errors.

- [ ] **Step 5: Audit repository state**

```bash
rtk git diff --check
rtk git status --short
rtk git log --oneline main..HEAD
```

Expected: no whitespace errors, no generated artifacts, and only intended feature commits.

- [ ] **Step 6: Commit any final in-scope documentation correction**

Only if verification required a documentation-only adjustment:

```bash
rtk git add README.md
rtk git add README.zh.md
rtk git commit -m "docs: clarify quota recovery behavior"
```

Otherwise leave the verified branch unchanged.
