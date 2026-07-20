# TUI Provider Visibility Design

> Allow hidden providers to disappear entirely from the interactive TUI top indicator, while keeping them accessible in the settings view for reordering and re-enabling.

## 1. Goal

In the interactive TUI (`-i` / `--interactive`), the top indicator currently shows **all** configured providers with `●` / `○` markers. Users who only want to monitor a subset of providers (e.g. four out of six) still see the remaining providers dimmed out, which clutters the header.

This design makes the top indicator show **only visible providers**. Hidden providers remain available in the settings view so they can be reordered or re-enabled at any time.

## 2. Current Behavior

- `AppConfig.visible_providers` already controls which providers are rendered in the main usage area.
- The settings view (`[s]`) lists every provider in `config.provider_order` and uses `●` / `○` to show visibility.
- Pressing `[1-6]` in either view toggles the visibility of the provider at that index.
- The top bar iterates over **all** `config.provider_order` entries, styling visible ones bold and hidden ones dim.

## 3. Proposed Design

### 3.1 Top Bar

The top bar iterates over **visible providers only**, in their configured order:

```python
visible_order = [p for p in config.provider_order if p in visible_providers]
for i, p in enumerate(visible_order, 1):
    short = _SHORT.get(p, p[:4].title())
    top_bar.append("● ", style="bold")
    top_bar.append(f"[{i}]{short}  ", style="bold")
```

Because every item in the bar is visible, the `○` marker and dim style are no longer needed in the top bar. They remain in the settings view.

### 3.2 Usage View Key Bindings

In the usage view, number keys target **visible providers only**, matching the indices shown in the top bar:

```python
providers = visible_order
if toggle_num is not None and toggle_num < len(providers):
    p = providers[toggle_num]
    visible_providers.discard(p)  # toggle off
```

This keeps the on-screen numbers consistent with the keys the user presses.

### 3.3 Settings View

The settings view continues to list **all** providers in `config.provider_order`:

- `●` = visible
- `○` = hidden
- Cursor (`▸`) highlights the selected row.
- `[1-N]` toggles visibility of the provider at that row.
- `↑/↓` moves the cursor.
- `←/→` reorders the selected provider within `config.provider_order`.

This gives users a single place to both hide providers and arrange their order, while the top bar stays clean.

### 3.4 Footer / Help Text

Update footer hints so the number range reflects the visible provider count in the usage view and the full provider count in the settings view:

- Usage view footer: `[1-M] panels` where `M = len(visible_order)`.
- Settings view footer: `[1-N] toggle panels` where `N = len(config.provider_order)`.
- Help text (`[h/?]`) explains that number keys target visible panels in usage view and all panels in settings view.

### 3.5 Persistence

No new config fields are introduced. The existing `general.visibleProviders` list in `~/.kimi-usage/config.json` is used as-is.

Pressing `Enter` persists the current `visible_providers` set via `save_theme(..., visible_providers=list(visible_providers), ...)`.

## 4. Edge Cases

| Case | Behavior |
|---|---|
| All providers hidden | Top bar shows a dim placeholder such as `(no visible panels)` / `（无可见面板）`. The main usage area shows the existing "No usage data found or no providers configured" message. |
| Only one provider visible | Top bar shows a single `● [1]Short` entry. Usage view `[1]` hides it. |
| Hidden provider reordered | Reordering in settings view updates `config.provider_order` immediately. If the provider is later re-enabled, it appears at its new position. |
| Saved config missing `visibleProviders` | Falls back to showing all providers, preserving current default behavior. |

## 5. Testing Plan

Add/update tests in `tests/test_main.py`:

1. **Settings rendering:** hidden providers appear with `○` and dim style, visible providers with `●` and bold style.
2. **Top bar after toggle:** after hiding providers, the top bar in usage view contains only the visible provider names.
3. **Usage view number keys:** pressing `[1]` in usage view hides the first visible provider (not necessarily `config.provider_order[0]`).
4. **Settings view number keys:** pressing `[5]` in settings view toggles `config.provider_order[4]` regardless of its current visibility.
5. **All hidden placeholder:** when `visible_providers` is empty, the top bar shows the localized placeholder text.
6. **Persistence:** pressing `Enter` writes the current visible provider list to the config file.

## 6. Files to Change

- `src/kimi_code_usage/main.py`
  - `_build_panel()` top bar construction.
  - `_interactive_mode()` key handling for number keys in usage vs. settings view.
  - Footer/hint rendering for dynamic number ranges.
- `tests/test_main.py`
  - New tests for top-bar visibility behavior and settings-view toggling.
