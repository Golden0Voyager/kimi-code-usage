# TUI Provider Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide invisible providers from the interactive TUI top indicator while keeping them accessible in the settings view.

**Architecture:** Reuse the existing `AppConfig.visible_providers` / `visibleProviders` mechanism. Compute `visible_order = [p for p in config.provider_order if p in visible_providers]` once per render and use it for the top bar and usage-view number-key handling. The settings view keeps rendering the full `provider_order` so users can toggle visibility and reorder. Persist on `Enter` as before.

**Tech Stack:** Python 3.11+, Rich, pytest, uv.

## Global Constraints

- No new config fields; reuse `general.visibleProviders`.
- Keep existing settings-view behavior: list all providers, `●`/`○` for visible/hidden, cursor reordering.
- Number keys in the usage view must match the indices shown in the top bar.
- Number keys in the settings view continue to address the full provider list.
- All existing tests must keep passing.

---

## Task 1: Top Bar Shows Only Visible Providers

**Files:**
- Modify: `src/kimi_code_usage/main.py:1244-1270` (`_build_panel` top bar construction)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `config.provider_order`, `visible_providers` set, `_SHORT` mapping.
- Produces: Top bar text containing only providers in `visible_order`.

- [ ] **Step 1: Write the failing test**

Add a test that simulates `_interactive_mode` with a config where only `kimi` is visible, then asserts the rendered top bar contains `[1]Kimi` and does **not** contain `[2]` or other provider short names.

```python
@pytest.mark.asyncio
async def test_interactive_mode_top_bar_shows_only_visible_providers(monkeypatch):
    """Top bar omits hidden providers and renumbers visible ones."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]
    cfg.visible_providers = ["kimi", "openai"]
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=1000, remaining=900, percent=10, reset_at=None, unit="tokens")],
    }

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    assert "[1]Kimi" in rendered
    assert "[2]ChatGPT+" in rendered or "[2]OpenAI API" in rendered  # depends on which is visible
    assert "[3]" not in rendered
    assert "[4]" not in rendered
    assert "[5]" not in rendered
    assert "[6]" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_top_bar_shows_only_visible_providers -v
```

Expected: FAIL because the current top bar renders all providers.

- [ ] **Step 3: Write minimal implementation**

In `src/kimi_code_usage/main.py`, inside `_build_panel()`, replace the top bar provider loop with:

```python
        top_bar = Text()
        visible_order = [p for p in config.provider_order if p in visible_providers]
        # Provider toggles (visible only)
        for i, p in enumerate(visible_order, 1):
            short = _SHORT.get(p, p[:4].title())
            top_bar.append("● ", style="bold")
            top_bar.append(f"[{i}]{short}  ", style="bold")
        if not visible_order:
            placeholder = "（无可见面板）" if lang_zh else "(no visible panels)"
            top_bar.append(placeholder, style="dim")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_top_bar_shows_only_visible_providers -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kimi_code_usage/main.py tests/test_main.py
git commit -m "feat(tui): top bar shows only visible providers

feat(tui): 顶部状态栏仅显示可见 provider"
```

---

## Task 2: Usage-View Number Keys Target Visible Providers

**Files:**
- Modify: `src/kimi_code_usage/main.py:1449-1456` (`_interactive_mode` toggle_num branch)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `toggle_num` from `_handle_key`, `visible_order` list.
- Produces: Updates `visible_providers` set by removing the selected visible provider.

- [ ] **Step 1: Write the failing test**

Add a test that opens the usage view, presses `2` to hide the second visible provider, and asserts the top bar no longer contains that provider's index.

```python
@pytest.mark.asyncio
async def test_interactive_mode_usage_number_key_targets_visible_order(monkeypatch):
    """Pressing [2] in usage view hides the second visible provider, not provider_order[1]."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["2", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic"]
    cfg.visible_providers = ["kimi", "anthropic"]  # openai is hidden
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "anthropic": [ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan")],
    }

    saved_calls = []
    def fake_save(theme, language=None, visible_providers=None, or_metric=None, days_window=None, config_path=None):
        saved_calls.append((theme, language, visible_providers, or_metric, days_window))

    with patch("kimi_code_usage.main.save_theme", fake_save):
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
            with patch("kimi_code_usage.main.Live") as mock_live_cls:
                mock_live = mock_live_cls.return_value.__enter__.return_value
                await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    # anthropic was at [2] in the visible top bar; pressing 2 should hide it
    assert "[2]Anthropic" not in rendered
    assert "[1]Kimi" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_usage_number_key_targets_visible_order -v
```

Expected: FAIL because the current code uses `config.provider_order` for number keys.

- [ ] **Step 3: Write minimal implementation**

In `src/kimi_code_usage/main.py`, inside `_interactive_mode`, change the `toggle_num` branch to:

```python
                    elif toggle_num is not None:
                        if current_view == "settings":
                            providers = list(config.provider_order)
                        else:
                            providers = [p for p in config.provider_order if p in visible_providers]
                        if toggle_num < len(providers):
                            p = providers[toggle_num]
                            if p in visible_providers:
                                visible_providers.discard(p)
                            else:
                                visible_providers.add(p)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_usage_number_key_targets_visible_order -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kimi_code_usage/main.py tests/test_main.py
git commit -m "feat(tui): usage-view number keys target visible providers

feat(tui): 用量视图数字键仅作用于可见 provider"
```

---

## Task 3: Settings View Keeps Full List and Toggle Works

**Files:**
- Modify: `src/kimi_code_usage/main.py:230-271` (`_render_setting_view`) if needed
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `config.provider_order`, `visible_providers` set.
- Produces: Settings view text with `●`/`○` markers and correct key hint `[1-N]`.

- [ ] **Step 1: Write the failing test**

Add a test that enters settings view (`s`), presses `2` to hide the second provider in the full list, and asserts the rendered panel shows that row as `○`.

```python
@pytest.mark.asyncio
async def test_interactive_mode_settings_number_key_toggles_full_list(monkeypatch):
    """In settings view, [2] toggles provider_order[1] even if it is not currently visible."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["s", "2", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic"]
    cfg.visible_providers = ["kimi", "anthropic"]  # openai starts hidden
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "anthropic": [ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan")],
    }

    saved_calls = []
    def fake_save(theme, language=None, visible_providers=None, or_metric=None, days_window=None, config_path=None):
        saved_calls.append((theme, language, visible_providers, or_metric, days_window))

    with patch("kimi_code_usage.main.save_theme", fake_save):
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
            with patch("kimi_code_usage.main.Live") as mock_live_cls:
                mock_live = mock_live_cls.return_value.__enter__.return_value
                await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    # After pressing 2 in settings, openai becomes visible
    assert "● [2] OpenAI API" in rendered or "● [2] OpenAI" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_settings_number_key_toggles_full_list -v
```

Expected: FAIL because the current code uses the same list for both views.

- [ ] **Step 3: Write minimal implementation**

No change to `_render_setting_view` is needed; it already renders the full list. The change from Task 2 already makes settings view use the full provider list. Verify the test passes after Task 2 is applied.

If the test still fails because the settings view hint text uses `max_keys = min(len(order), 9)` and does not match expectations, leave it as-is — it already reflects the full list length.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_settings_number_key_toggles_full_list -v
```

Expected: PASS (after Task 2 implementation).

- [ ] **Step 5: Commit**

```bash
git add tests/test_main.py
git commit -m "test(tui): settings-view number keys toggle full provider list

test(tui): 设置视图数字键可切换完整 provider 列表"
```

---

## Task 4: Footer Hints and Help Text Reflect Visible Provider Count

**Files:**
- Modify: `src/kimi_code_usage/main.py:1272-1287` (`_interactive_mode` footer bindings)
- Modify: `src/kimi_code_usage/main.py:274-314` (`_render_interactive_help`)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `current_view`, `visible_order`, `config.provider_order`, `lang_zh`.
- Produces: Footer hint `[1-M] panels` in usage view and `[1-N] panels` in settings view; help text describing the two modes.

- [ ] **Step 1: Write the failing test**

Add a test that checks the footer in usage view uses `[1-2]` when two providers are visible, and `[1-6]` in settings view when six providers exist.

```python
@pytest.mark.asyncio
async def test_interactive_mode_footer_hints_reflect_visible_count(monkeypatch):
    """Footer number range matches visible count in usage view and full count in settings view."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["s", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]
    cfg.visible_providers = ["kimi", "openai"]
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=1000, remaining=900, percent=10, reset_at=None, unit="tokens")],
    }

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    # Usage view before 's' should show [1-2]
    # Settings view after 's' should show [1-6]
    # Because the test renders both views, assert both ranges appear at some point.
    assert "[1-2]" in rendered
    assert "[1-6]" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_footer_hints_reflect_visible_count -v
```

Expected: FAIL because the footer always uses `len(config.provider_order)`.

- [ ] **Step 3: Write minimal implementation**

In `src/kimi_code_usage/main.py`, inside `_build_panel()`, compute the panel key range based on the current view:

```python
        hint = Text()
        if current_view == "settings":
            panel_range = str(len(config.provider_order))
        else:
            panel_range = str(len(visible_order))
        bindings = [
            ("[q]", "退出" if lang_zh else "quit"),
            ("[r]", "刷新" if lang_zh else "refresh"),
            ("[h/?]", "帮助" if lang_zh else "help"),
            ("[c]", "配置" if lang_zh else "config"),
            ("[s]", "设置" if lang_zh else "settings"),
            ("[←/→]", "主题" if lang_zh else "theme"),
            (f"[1-{panel_range}]", "面板" if lang_zh else "panels"),
            ("[↑↓]", "滚动" if lang_zh else "scroll"),
            ("[l]", "英" if lang_zh else "ZH"),
            ("[m]", _metric_label(or_metric, lang_zh)),
            ("[d]", f"{days_window}d"),
            ("[⏎ ]", "保存" if lang_zh else "save"),
        ]
```

Then update `_render_interactive_help` to clarify the two modes. Replace the existing `([1-6], ...)` row with two rows:

```python
            ("1-N (usage)", "切换可见服务商面板"),
            ("1-N (settings)", "切换任意服务商显示/隐藏"),
```

For English:

```python
            ("1-N (usage)", "toggle visible provider panels"),
            ("1-N (settings)", "toggle any provider visibility"),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_footer_hints_reflect_visible_count -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kimi_code_usage/main.py tests/test_main.py
git commit -m "feat(tui): footer and help text reflect visible provider count

feat(tui): 底部提示和帮助文本根据可见 provider 数量动态调整"
```

---

## Task 5: All-Hidden Placeholder in Top Bar

**Files:**
- Modify: `src/kimi_code_usage/main.py:1256-1265` (top bar placeholder from Task 1)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `visible_order`, `lang_zh`.
- Produces: Dim placeholder text in the top bar when no provider is visible.

- [ ] **Step 1: Write the failing test**

Add a test that initializes with `visible_providers = []` and asserts the top bar shows the placeholder.

```python
@pytest.mark.asyncio
async def test_interactive_mode_top_bar_placeholder_when_all_hidden(monkeypatch):
    """When all providers are hidden, top bar shows a dim placeholder."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai"]
    cfg.visible_providers = []
    mock_res = {}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    assert "(no visible panels)" in rendered or "（无可见面板）" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_top_bar_placeholder_when_all_hidden -v
```

Expected: FAIL because the current top bar renders nothing or all providers when none are visible.

- [ ] **Step 3: Write minimal implementation**

The placeholder was already added in Task 1. Ensure it is inside the top bar loop and styled dim. No further code change is required if Task 1 was implemented correctly.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py::test_interactive_mode_top_bar_placeholder_when_all_hidden -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_main.py
git commit -m "test(tui): placeholder when all providers hidden

test(tui): 全部 provider 隐藏时顶部占位文本"
```

---

## Task 6: Regression Run

**Files:**
- All modified files.

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest --cov=kimi_code_usage --cov-report=term-missing
```

Expected: All tests pass; coverage for modified lines meets the project target (100%).

- [ ] **Step 2: Run lint/format checks**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: No lint errors; formatting is clean.

- [ ] **Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "chore: address review feedback / lint fixes

chore: 修复审查意见和 lint 问题"
```

---

## Self-Review Checklist

- [ ] Spec coverage: top bar visibility, usage-view number keys, settings-view full list, footer hints, help text, all-hidden placeholder, persistence — all have tasks.
- [ ] No placeholders: every step has concrete code or command.
- [ ] Type consistency: `visible_providers` remains a `set`; `visible_order` is a `list[str]`.
