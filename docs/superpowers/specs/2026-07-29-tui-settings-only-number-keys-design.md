# TUI Settings-Only Number Keys Design

## Goal

Prevent accidental provider-panel hiding when a user presses `1`–`6` in the
normal interactive usage view. Number keys remain available only inside the
panel settings view.

## Current Behavior

The interactive TUI routes number keys through the shared key handler in every
view. In the usage view, the number targets the provider at the matching
position in the visible-provider list and hides it. The top bar, footer, and
help page also advertise this behavior with numbered provider labels and
`[1-N] panels` hints.

The settings view separately lists all configured providers with numbered
rows, where number keys toggle each provider's visibility.

## Selected Approach

Use a minimal view guard around the existing number-key toggle path:

- Process a parsed number key only when `current_view == "settings"`.
- Ignore number keys in the usage, help, and configuration views.
- Continue using `config.provider_order` as the settings-view number mapping.
- Do not introduce new configuration fields or change persistence.

This keeps the established settings behavior while removing the accidental
action from the base TUI. A larger per-view keymap refactor is outside scope.

## User Interface

### Usage, Help, and Configuration Views

- The top provider indicator uses unnumbered labels such as
  `● Kimi  ● ChatGPT+`.
- The footer does not show a number-key panel binding.
- The help page does not describe number keys as available in the usage view.
- Pressing `1`–`6` has no effect on provider visibility.

### Settings View

- Provider rows remain numbered, for example `● [1] Kimi` and
  `○ [2] OpenAI API`.
- The settings instructions and footer retain the `[1-N] toggle panels`
  binding.
- Pressing a valid number toggles the corresponding entry in
  `config.provider_order`.
- Out-of-range number keys remain no-ops.

The global top provider indicator remains unnumbered even while the settings
body is displayed; the numbered settings rows are the sole visual mapping for
the shortcut.

## Data and Persistence

No data model changes are required. The settings view continues to mutate the
in-memory `visible_providers` set. Pressing Enter continues to persist that set
through the existing `save_theme(..., visible_providers=...)` path.

Ignoring a number key outside settings does not mutate or persist any state.

## Testing

Update `tests/test_main.py` using the existing interactive terminal harness:

1. Pressing a number in the usage view leaves every visible provider visible.
2. The usage-view top bar contains provider names without `[1]`–`[6]` labels.
3. The usage-view footer omits the `[1-N] panels` binding.
4. The help page omits the usage-view number-key description.
5. The settings view still shows `[1-N] toggle panels`.
6. Pressing a number in settings still toggles the matching full-order
   provider.

Run the focused interactive tests first, then the complete test suite, Ruff,
and the configured coverage check.

## Files in Scope

- `src/kimi_code_usage/main.py`
  - Interactive help text.
  - Top-bar provider labels.
  - Footer bindings.
  - Number-key dispatch guard.
  - Interactive-mode docstring.
- `tests/test_main.py`
  - Usage-view no-op and presentation regressions.
  - Existing settings-view behavior regression.

## Out of Scope

- Changing settings persistence or provider ordering.
- Replacing settings number keys with Space or Enter.
- Changing arrow-key, theme, refresh, language, metric, or save bindings.
- Modifying non-interactive CLI, MCP, web dashboard, or VS Code behavior.
