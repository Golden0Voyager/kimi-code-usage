# TUI Settings-Only Number Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make number keys no-ops outside the TUI settings view while preserving numbered visibility toggles inside settings.

**Architecture:** Keep the existing shared `_handle_key()` parser and add the view boundary at the `_interactive_mode()` dispatch point. Update the top bar, footer, help copy, and interactive docstring so only the settings body advertises numbered provider controls.

**Tech Stack:** Python 3.12, asyncio, Rich Live/Text/Panel, pytest, pytest-asyncio, unittest.mock, Ruff

## Global Constraints

- Number keys are actionable only when `current_view == "settings"`.
- Usage, help, and configuration views ignore number keys without mutating or persisting state.
- The global top provider indicator is unnumbered in every view.
- The settings provider rows and `[1-N] toggle panels` hint remain numbered.
- No configuration schema, persistence, non-interactive CLI, MCP, web dashboard, or VS Code changes.
- Production changes must follow red-green-refactor TDD.

---

### Task 1: Restrict Number-Key Dispatch to Settings

**Files:**
- Modify: `tests/test_main.py:826-880`
- Modify: `src/kimi_code_usage/main.py:1543-1561`

**Interfaces:**
- Consumes: `_handle_key(ch: str, idx: int, theme_count: int)`, which returns `toggle_num` as a zero-based index for digit keys.
- Produces: `_interactive_mode()` behavior in which `toggle_num` mutates `visible_providers` only for the settings view.

- [ ] **Step 1: Replace the usage-view toggle regression with a no-op regression**

Replace `test_interactive_mode_usage_number_key_targets_visible_order` with:

```python
@pytest.mark.asyncio
async def test_interactive_mode_usage_number_key_is_ignored(monkeypatch):
    """Pressing a number in usage view leaves visible providers unchanged."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["2", "q"])
    import kimi_code_usage.main as main_mod

    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic"]
    cfg.visible_providers = ["kimi", "anthropic"]
    mock_res = {
        "kimi": [
            ProviderUsage(
                provider="kimi",
                label="Weekly Usage",
                used=5,
                limit=100,
                remaining=95,
                percent=5,
                reset_at=None,
                unit="%",
            )
        ],
        "anthropic": [
            ProviderUsage(
                provider="anthropic",
                label="API Plan",
                used=0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                text_value="Pro Plan",
            )
        ],
    }

    with patch(
        "kimi_code_usage.main.dispatch_all",
        AsyncMock(return_value=(mock_res, {})),
    ):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(
        _panel_plain(call.args[0])
        for call in mock_live.update.call_args_list
    )
    assert "Kimi" in rendered
    assert "Anthropic" in rendered
    assert "Pro Plan" in rendered
```

- [ ] **Step 2: Run the new regression and verify RED**

Run:

```bash
rtk uv run python -m pytest tests/test_main.py::test_interactive_mode_usage_number_key_is_ignored -q
```

Expected: FAIL because pressing `2` currently removes Anthropic, so `"Anthropic"` and `"Pro Plan"` are absent from the rendered update.

- [ ] **Step 3: Add the minimal settings-view guard**

Replace the existing `elif toggle_num is not None:` branch in `_interactive_mode()` with:

```python
elif toggle_num is not None and current_view == "settings":
    providers = list(config.provider_order)
    if toggle_num < len(providers):
        p = providers[toggle_num]
        if p in visible_providers:
            visible_providers.discard(p)
        else:
            visible_providers.add(p)
```

No separate usage-view branch is retained. A number parsed in any other view falls through as a no-op before the panel is redrawn.

- [ ] **Step 4: Verify GREEN for usage and settings behavior**

Run:

```bash
rtk uv run python -m pytest \
  tests/test_main.py::test_interactive_mode_usage_number_key_is_ignored \
  tests/test_main.py::test_interactive_mode_settings_number_key_toggles_full_list \
  -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit the behavior boundary**

```bash
rtk git add tests/test_main.py src/kimi_code_usage/main.py
rtk git commit -m "fix: limit TUI number keys to settings"
```

---

### Task 2: Remove Number-Key Affordances Outside Settings

**Files:**
- Modify: `tests/test_main.py:707-743`
- Modify: `tests/test_main.py:745-796`
- Modify: `tests/test_main.py:941-992`
- Modify: `src/kimi_code_usage/main.py:310-344`
- Modify: `src/kimi_code_usage/main.py:1282-1290`
- Modify: `src/kimi_code_usage/main.py:1348-1387`

**Interfaces:**
- Consumes: `_render_interactive_help()`, `_interactive_mode()` and its nested `_build_panel()`.
- Produces: unnumbered global provider labels, settings-only numeric footer help, and help copy that names only the settings number binding.

- [ ] **Step 1: Update presentation regressions before production code**

In `test_interactive_mode_help_and_config_keys`, add:

```python
assert "1-N (usage)" not in rendered
assert "1-N (settings)" in rendered
```

Rename `test_interactive_mode_top_bar_shows_only_visible_providers` to
`test_interactive_mode_top_bar_shows_unnumbered_visible_providers`, update its
docstring to `"Top bar shows visible providers without shortcut numbers."`,
and replace its final assertions with:

```python
assert "● Kimi" in rendered
assert "● ChatGPT+" in rendered or "● OpenAI API" in rendered
assert "[1]Kimi" not in rendered
assert "[2]ChatGPT+" not in rendered
assert "[2]OpenAI API" not in rendered
```

Rename `test_interactive_mode_footer_hints_reflect_visible_count` to
`test_interactive_mode_footer_number_hint_is_settings_only`, update its
docstring to `"Only the settings view advertises number-key panel toggles."`,
and replace its final assertions with:

```python
assert "[1-2]" not in rendered
assert "[1-6]" in rendered
assert "toggle panels" in rendered or "开关面板" in rendered
```

- [ ] **Step 2: Run the presentation regressions and verify RED**

Run:

```bash
rtk uv run python -m pytest \
  tests/test_main.py::test_interactive_mode_help_and_config_keys \
  tests/test_main.py::test_interactive_mode_top_bar_shows_unnumbered_visible_providers \
  tests/test_main.py::test_interactive_mode_footer_number_hint_is_settings_only \
  -q
```

Expected: all three tests FAIL because the help still describes usage digits,
the top bar is numbered, and the usage footer still contains `[1-2]`.

- [ ] **Step 3: Remove the usage-view number help row**

In `_render_interactive_help()`, remove these two rows:

```python
("1-N (usage)", "切换可见服务商面板"),
("1-N (usage)", "toggle visible provider panels"),
```

Keep both settings rows unchanged:

```python
("1-N (settings)", "切换任意服务商显示/隐藏"),
("1-N (settings)", "toggle any provider visibility"),
```

- [ ] **Step 4: Make global top-bar labels unnumbered**

Replace the numbered loop with:

```python
for p in visible_order:
    short = _SHORT.get(p, p[:4].title())
    top_bar.append("● ", style="bold")
    top_bar.append(f"{short}  ", style="bold")
```

Update the preceding comment to:

```python
# Visible provider indicators; numeric shortcuts are settings-only.
```

- [ ] **Step 5: Restrict the numeric footer binding to settings**

Replace the `panel_range` selection with:

```python
panel_range = (
    str(len(config.provider_order))
    if current_view == "settings"
    else None
)
```

Replace the conditional binding insertion with:

```python
if panel_range is not None:
    panel_label = "开关面板" if lang_zh else "toggle panels"
    bindings.insert(6, (f"[1-{panel_range}]", panel_label))
```

- [ ] **Step 6: Correct the interactive-mode docstring**

Replace the number-key line in `_interactive_mode()` with:

```text
        1–9 (settings only) — toggle provider panels
```

The surrounding theme, refresh, and quit key descriptions remain unchanged.

- [ ] **Step 7: Verify GREEN for all affected interactive tests**

Run:

```bash
rtk uv run python -m pytest tests/test_main.py -q
```

Expected: all `tests/test_main.py` tests pass, including the unchanged settings-view number toggle regression.

- [ ] **Step 8: Run full project verification**

Run:

```bash
rtk uv run ruff check .
rtk uv run python -m pytest --cov=kimi_code_usage --cov-report=term-missing -q
```

Expected:

- Ruff exits `0`.
- The complete suite passes.
- Coverage is at least the configured `85%` threshold.
- Only previously known warnings may remain; no new warning is introduced by this change.

- [ ] **Step 9: Commit the presentation cleanup**

```bash
rtk git add tests/test_main.py src/kimi_code_usage/main.py
rtk git commit -m "fix: remove TUI number hints outside settings"
```

- [ ] **Step 10: Confirm final branch state**

Run:

```bash
rtk git diff --check main..HEAD
rtk git status --short --branch
rtk git log --oneline main..HEAD
```

Expected:

- `git diff --check` exits `0`.
- The worktree is clean on `fix/tui-settings-only-number-keys`.
- The design, plan, behavior, and presentation commits are all listed.
