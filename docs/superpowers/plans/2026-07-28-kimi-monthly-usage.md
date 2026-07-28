# Kimi Monthly Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `uv run kimi-usage` append the Kimi membership monthly usage shown on the logged-in subscription page, without disrupting existing weekly and 5-hour usage data.

**Architecture:** A new `kimi_membership` module has a pure snapshot parser and a small localhost WebBridge client. `fetch_kimi_usage` keeps `/usages` as its primary source and appends either a normalized monthly `ProviderUsage` or a text-only unavailable record; it never converts a membership-reader failure into a provider-wide failure.

**Tech Stack:** Python 3.12, aiohttp, existing `ProviderUsage` model, pytest with asyncio mode, Kimi WebBridge localhost command API.

## Global Constraints

- Read only the logged-in browser session; never persist cookies, tokens, raw snapshots, or account identifiers.
- Use the subscription page accessibility snapshot, not an undocumented Kimi HTTP endpoint.
- Keep `/usages` weekly and 5-hour behavior unchanged when WebBridge is absent, disconnected, timed out, logged out, or changed.
- First release changes only `uv run kimi-usage` and `--json`; do not add MCP, web-panel, or VS Code integration.
- Tests must use synthetic, non-account snapshot data and must not require a browser or network.

---

## File Structure

- Create: `src/kimi_code_usage/providers/kimi_membership.py` — extracts a monthly usage record from a WebBridge snapshot and reads the snapshot through the localhost bridge.
- Modify: `src/kimi_code_usage/providers/kimi.py` — appends monthly usage or an unavailable text record after successful `/usages` parsing.
- Modify: `tests/test_provider_kimi.py` — verifies existing Kimi output remains unchanged and gains monthly integration coverage.
- Create: `tests/test_provider_kimi_membership.py` — tests pure snapshot parsing and bridge error behavior with synthetic payloads.
- Modify: `README.md` and `README.zh.md` — document the optional logged-in-browser prerequisite and degraded behavior.

### Task 1: Parse a subscription accessibility snapshot

**Files:**

- Create: `src/kimi_code_usage/providers/kimi_membership.py`
- Test: `tests/test_provider_kimi_membership.py`

**Interfaces:**

- Produces: `parse_monthly_usage_snapshot(snapshot: Mapping[str, Any], *, lang_zh: bool) -> ProviderUsage | None`
- Produces: `MonthlyUsageUnavailable` for expected local-browser failures.
- Consumes: `ProviderUsage` from `kimi_code_usage.providers`.

- [ ] **Step 1: Write the failing parser tests**

```python
from kimi_code_usage.providers.kimi_membership import parse_monthly_usage_snapshot


def test_parse_monthly_usage_snapshot_reads_first_total_card_in_usage_progress():
    snapshot = {
        "tree": [[
            {"role": "heading", "name": "用量进度"},
            {"role": "StaticText", "name": "总使用量"},
            {"role": "StaticText", "name": "62%"},
            {"role": "StaticText", "name": "Kimi Code"},
            {"role": "StaticText", "name": "2026-08-12 后重置"},
            {"role": "heading", "name": "赠送额度"},
            {"role": "StaticText", "name": "总使用量"},
            {"role": "StaticText", "name": "100%"},
        ]]
    }

    row = parse_monthly_usage_snapshot(snapshot, lang_zh=False)

    assert row is not None
    assert row.label == "Monthly Credits"
    assert row.used == 62.0
    assert row.limit == 100.0
    assert row.remaining == 38.0
    assert row.percent == 62.0
    assert row.reset_at == "2026-08-12"
    assert row.unit == "%"


def test_parse_monthly_usage_snapshot_returns_none_without_usage_progress_card():
    assert parse_monthly_usage_snapshot({"tree": [[{"role": "StaticText", "name": "账户"}]]}, lang_zh=True) is None
```

- [ ] **Step 2: Run the parser tests and verify RED**

Run: `rtk uv run pytest tests/test_provider_kimi_membership.py -v`

Expected: FAIL during collection because `kimi_code_usage.providers.kimi_membership` does not exist.

- [ ] **Step 3: Implement the pure parser**

```python
class MonthlyUsageUnavailable(Exception):
    """A recoverable failure while reading the local Kimi subscription page."""


def _flatten_names(node: Any) -> list[str]:
    if isinstance(node, list):
        return [name for item in node for name in _flatten_names(item)]
    if not isinstance(node, Mapping):
        return []
    names = [str(node["name"])] if isinstance(node.get("name"), str) else []
    return names + _flatten_names(node.get("children", []))


def parse_monthly_usage_snapshot(snapshot: Mapping[str, Any], *, lang_zh: bool) -> ProviderUsage | None:
    names = _flatten_names(snapshot.get("tree", []))
    start = next((i for i, value in enumerate(names) if value in {"用量进度", "Usage Progress"}), None)
    if start is None:
        return None
    end = next((i for i, value in enumerate(names[start + 1:], start + 1) if value in {"赠送额度", "Bonus Credits"}), len(names))
    card = names[start:end]
    total = next((i for i, value in enumerate(card) if value in {"总使用量", "Total Usage"}), None)
    if total is None:
        return None
    match = next((re.fullmatch(r"(\\d+(?:\\.\\d+)?)%", value) for value in card[total + 1:] if re.fullmatch(r"(\\d+(?:\\.\\d+)?)%", value)), None)
    if match is None:
        return None
    used = float(match.group(1))
    reset = next((re.search(r"(\\d{4}-\\d{2}-\\d{2}).*(?:后重置|reset)", value, re.I) for value in card[total + 1:] if re.search(r"\\d{4}-\\d{2}-\\d{2}.*(?:后重置|reset)", value, re.I)), None)
    return ProviderUsage("kimi", "月度额度" if lang_zh else "Monthly Credits", used, 100.0, 100.0 - used, used, reset.group(1) if reset else None, "%")
```

Add `import re`, `from collections.abc import Mapping`, `from typing import Any`, and `from . import ProviderUsage` at the top of the new file. Keep `_flatten_names` private.

- [ ] **Step 4: Run the parser tests and verify GREEN**

Run: `rtk uv run pytest tests/test_provider_kimi_membership.py -v`

Expected: PASS, 2 passed.

- [ ] **Step 5: Commit the parser slice**

```bash
rtk git add src/kimi_code_usage/providers/kimi_membership.py tests/test_provider_kimi_membership.py
rtk git commit -m "feat: parse Kimi membership monthly usage"
```

### Task 2: Read the snapshot through Kimi WebBridge

**Files:**

- Modify: `src/kimi_code_usage/providers/kimi_membership.py`
- Test: `tests/test_provider_kimi_membership.py`

**Interfaces:**

- Produces: `async def fetch_monthly_usage_from_webbridge(*, lang_zh: bool) -> ProviderUsage`
- Consumes: `parse_monthly_usage_snapshot(snapshot, lang_zh=lang_zh)` from Task 1.
- Raises: `MonthlyUsageUnavailable` with a user-actionable, non-sensitive explanation.

- [ ] **Step 1: Write the failing WebBridge-client tests**

```python
import pytest
from unittest.mock import AsyncMock, patch

from kimi_code_usage.providers.kimi_membership import (
    MonthlyUsageUnavailable,
    fetch_monthly_usage_from_webbridge,
)


@pytest.mark.asyncio
async def test_fetch_monthly_usage_requests_snapshot_after_reusing_subscription_tab():
    responses = [
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"url": "https://www.kimi.com/membership/subscription?tab=quota"}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)) as command:
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert row.used == 25.0
    assert [call.args[0] for call in command.await_args_list] == ["find_tab", "snapshot"]


@pytest.mark.asyncio
async def test_fetch_monthly_usage_opens_subscription_page_when_not_already_open():
    responses = [
        {"ok": True, "data": {"success": False}},
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
        {"ok": True, "data": {"closed": True}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)) as command:
        await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert [call.args[0] for call in command.await_args_list] == ["find_tab", "navigate", "snapshot", "close_tab"]


@pytest.mark.asyncio
async def test_fetch_monthly_usage_explains_disconnected_bridge():
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(return_value={"ok": False, "error": "connection refused"})):
        with pytest.raises(MonthlyUsageUnavailable, match="WebBridge"):
            await fetch_monthly_usage_from_webbridge(lang_zh=False)
```

- [ ] **Step 2: Run the WebBridge tests and verify RED**

Run: `rtk uv run pytest tests/test_provider_kimi_membership.py -v`

Expected: FAIL because `_bridge_command` and `fetch_monthly_usage_from_webbridge` are not defined.

- [ ] **Step 3: Implement the bounded localhost client**

```python
_BRIDGE_URL = "http://127.0.0.1:10086/command"
_SUBSCRIPTION_URL = "https://www.kimi.com/membership/subscription?tab=quota"
_SESSION = "kimi-usage"


async def _bridge_command(action: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
    timeout = aiohttp.ClientTimeout(total=3)
    payload = {"action": action, "args": dict(args), "session": _SESSION}
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_BRIDGE_URL, json=payload) as response:
            if response.status != 200:
                raise MonthlyUsageUnavailable("Kimi WebBridge is unavailable; start it and open the browser extension.")
            data = await response.json()
    if not isinstance(data, Mapping) or not data.get("ok"):
        raise MonthlyUsageUnavailable("Kimi WebBridge is unavailable; start it and open the browser extension.")
    return data


async def fetch_monthly_usage_from_webbridge(*, lang_zh: bool) -> ProviderUsage:
    found = await _bridge_command("find_tab", {"url": _SUBSCRIPTION_URL, "active": False})
    opened = not bool((found.get("data") or {}).get("success"))
    if opened:
        await _bridge_command("navigate", {"url": _SUBSCRIPTION_URL, "newTab": True, "group_title": "Kimi Usage"})
    try:
        snapshot_response = await _bridge_command("snapshot", {})
        data = snapshot_response.get("data")
        row = parse_monthly_usage_snapshot(data if isinstance(data, Mapping) else {}, lang_zh=lang_zh)
        if row is None:
            raise MonthlyUsageUnavailable("Kimi monthly usage was not found; log in and open the Subscription page.")
        return row
    finally:
        if opened:
            await _bridge_command("close_tab", {})
```

Import `aiohttp`. Convert `aiohttp.ClientError`, `asyncio.TimeoutError`, and malformed bridge responses into `MonthlyUsageUnavailable`; do not include raw response text in the exception.

- [ ] **Step 4: Run the WebBridge tests and verify GREEN**

Run: `rtk uv run pytest tests/test_provider_kimi_membership.py -v`

Expected: PASS, 5 passed.

- [ ] **Step 5: Commit the WebBridge reader slice**

```bash
rtk git add src/kimi_code_usage/providers/kimi_membership.py tests/test_provider_kimi_membership.py
rtk git commit -m "feat: read Kimi monthly usage from WebBridge"
```

### Task 3: Append monthly usage without degrading Kimi API output

**Files:**

- Modify: `src/kimi_code_usage/providers/kimi.py`
- Modify: `tests/test_provider_kimi.py`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**

- Consumes: `fetch_monthly_usage_from_webbridge(lang_zh: bool) -> ProviderUsage` and `MonthlyUsageUnavailable` from Task 2.
- Produces: `fetch_kimi_usage(...) -> list[ProviderUsage]` whose first item is either `Monthly Credits`/`月度额度` or a text-only unavailable row; remaining items preserve existing API order.

- [ ] **Step 1: Write the failing integration tests**

```python
@pytest.mark.asyncio
async def test_fetch_kimi_usage_appends_monthly_usage_from_webbridge():
    monthly = ProviderUsage("kimi", "Monthly Credits", 62.0, 100.0, 38.0, 62.0, "2026-08-12", "%")
    with patch("kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge", new=AsyncMock(return_value=monthly)):
        with patch("aiohttp.ClientSession", return_value=mock_session_for({"data": [{"model_name": "all", "limit": 100, "used": 14}]})):
            rows = await fetch_kimi_usage("test-key", "https://api.example.com/v1")

    assert [row.label for row in rows] == ["Monthly Credits", "Weekly Usage"]


@pytest.mark.asyncio
async def test_fetch_kimi_usage_keeps_api_rows_when_monthly_reader_is_unavailable():
    with patch("kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge", new=AsyncMock(side_effect=MonthlyUsageUnavailable("Kimi WebBridge is unavailable"))):
        with patch("aiohttp.ClientSession", return_value=mock_session_for({"data": [{"model_name": "all", "limit": 100, "used": 14}]})):
            rows = await fetch_kimi_usage("test-key", "https://api.example.com/v1")

    assert rows[0].label == "Monthly Credits"
    assert rows[0].unit == "text"
    assert "WebBridge" in rows[0].text_value
    assert rows[1].label == "Weekly Usage"
```

Add a local `mock_session_for` helper beside the existing async HTTP mocks. Import `ProviderUsage` and `MonthlyUsageUnavailable` in this test file.

- [ ] **Step 2: Run the integration tests and verify RED**

Run: `rtk uv run pytest tests/test_provider_kimi.py -k 'monthly_usage' -v`

Expected: FAIL because `fetch_kimi_usage` does not yet import or append the membership reader.

- [ ] **Step 3: Append the monthly record after the `/usages` rows**

```python
from .kimi_membership import MonthlyUsageUnavailable, fetch_monthly_usage_from_webbridge


async def _monthly_usage_row() -> ProviderUsage:
    try:
        return await fetch_monthly_usage_from_webbridge(lang_zh=_KIMI_LANG_IS_ZH)
    except MonthlyUsageUnavailable as exc:
        return ProviderUsage(
            provider="kimi",
            label="月度额度" if _KIMI_LANG_IS_ZH else "Monthly Credits",
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value=str(exc),
        )
```

At the end of `fetch_kimi_usage`, replace `return res` with:

```python
return [await _monthly_usage_row(), *res]
```

Do not catch errors from the primary `/usages` request. Its existing error behavior remains unchanged.

- [ ] **Step 4: Run focused tests and full suite**

Run: `rtk uv run pytest tests/test_provider_kimi.py -k 'monthly_usage or fetch_kimi_usage' -v`

Expected: PASS.

Run: `rtk uv run pytest`

Expected: PASS with the pre-existing three runtime warnings only.

- [ ] **Step 5: Document the browser prerequisite and commit**

Add this note below the Kimi API key setup section in both READMEs:

```markdown
Monthly membership usage is optional. To display it, keep Kimi WebBridge running, the browser extension connected, and a logged-in Kimi browser session available. If it is unavailable, weekly and 5-hour Kimi usage still work normally.
```

Translate the Chinese README note as:

```markdown
月度会员额度为可选增强功能。请保持 Kimi WebBridge 运行、浏览器扩展已连接且 Kimi 已登录；不可用时，周用量和 5 小时用量仍会正常显示。
```

Then run:

```bash
rtk git add src/kimi_code_usage/providers/kimi.py tests/test_provider_kimi.py README.md README.zh.md
rtk git commit -m "feat: show Kimi monthly membership usage"
```

### Task 4: Verify JSON output and static quality

**Files:**

- Modify: `tests/test_main.py` only if the current JSON serialization test lacks a Kimi record assertion.

**Interfaces:**

- Consumes: `ProviderUsage` monthly records produced by Task 3.
- Produces: `uv run kimi-usage --json` includes a Kimi monthly record unchanged by serialization.

- [ ] **Step 1: Write the failing CLI JSON test**

```python
def test_main_json_output_preserves_kimi_monthly_record(monkeypatch, capsys):
    monthly = ProviderUsage("kimi", "Monthly Credits", 62.0, 100.0, 38.0, 62.0, "2026-08-12", "%")
    monkeypatch.setattr(main_mod, "dispatch_all", AsyncMock(return_value=({"kimi": [monthly]}, {})))
    monkeypatch.setattr(sys, "argv", ["kimi-usage", "--json"])

    main_mod.run_cli()

    payload = json.loads(capsys.readouterr().out)
    assert payload["kimi"][0]["label"] == "Monthly Credits"
    assert payload["kimi"][0]["remaining"] == 38.0
```

- [ ] **Step 2: Run the JSON test and verify RED or existing coverage**

Run: `rtk uv run pytest tests/test_main.py -k 'json_output_preserves_kimi_monthly_record' -v`

Expected: FAIL if a new assertion is necessary. If the existing JSON serializer already passes the exact record unchanged, record that evidence and do not add duplicate production code.

- [ ] **Step 3: Make only the minimal serialization change if RED proves one is needed**

Use the existing `ProviderUsage` JSON serialization path. Do not add a Kimi-specific serializer.

- [ ] **Step 4: Run final checks**

Run: `rtk uv run pytest`

Expected: all tests pass.

Run: `rtk uv run ruff check .`

Expected: no lint violations.

Run: `rtk git status --short`

Expected: only intended tracked changes before the final verification commit, then clean after it.

- [ ] **Step 5: Commit any necessary JSON test**

```bash
rtk git add tests/test_main.py
rtk git commit -m "test: cover Kimi monthly usage JSON output"
```
