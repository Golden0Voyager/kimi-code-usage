# Round 2 — Monthly / extra-usage parity and npm hygiene

Date: 2026-10-20
Branch: `feat/round2-monthly-ux`
Base: `main` @ `28eaf88` (merge of PR #21, round 1)

## Why

Round 1 cleared the pip advisories and closed the extension's CI/format gaps.
Two visible gaps remained between the Python provider and the VS Code
extension, plus the npm advisories that came with tracking the lock:

1. the extension never showed an "Extra Usage" row when the wallet was
   disabled — the exact state of the maintainer's own account, and the reason
   the earlier `booster_wallet` fix had no visible effect in the editor;
2. the wallet gate disagreed with upstream `MoonshotAI/kimi-code`, which keeps
   `monthlyChargeLimitEnabled` separate from `status` and reads a newer
   `balance` object instead of `status`;
3. `vscode-extension/package-lock.json` carried 8-9 dev-only advisories.

## Non-goals

- No `fastmcp` 3→4 / `mcp` 1→2 upgrade (round 3, needs a real MCP smoke).
- No change to how `(web)` monthly credits are fetched or labelled.
- No new money-formatting surface beyond the existing `¥{amount}` convention
  the Python provider already uses.

## Decisions

### D1 — the wallet is active when *any* positive signal is present

The user asked which wins when `status` and `monthlyChargeLimitEnabled`
disagree. Upstream evidence (`packages/oauth/src/managed-usage.ts`):

- upstream never reads `status`; it requires `balance.type === "BOOSTER"` with
  `amount > 0`, and exposes `monthlyChargeLimitEnabled` as data;
- the live payload we probed has **neither** `balance` nor
  `monthlyChargeLimitEnabled`, so copying upstream verbatim would hide the row
  entirely.

Therefore neither signal vetoes the other:

```
active = status == "STATUS_ENABLED"
      or monthlyChargeLimitEnabled == true   (camelCase or snake_case)
      or balance.type == "BOOSTER" and balance.amount > 0
```

Same rule in both surfaces (`api.ts`, `kimi.py`). A disabled wallet produces a
literal row (`Not enabled` / `未开启`), which is what makes the row visible at
all on the maintainer's account.

### D2 — `(web)` source marker is not applicable to the extension

Python's `(web)` label disambiguates **two** monthly sources: the OAuth API
(`fetch_monthly_usage_from_oauth`) and a real browser snapshot via WebBridge
(`fetch_monthly_usage_from_webbridge` → `Monthly Credits (web)`). The extension
only has the OAuth/CLI-token path, so there is nothing to disambiguate; adding
`(web)` there would be a false claim. Dropped from scope, documented here.

### D3 — a zero cap reports spending, not "100% left"

Python already emits `¥{used}` when `monthlyChargeLimit` is 0. The extension
printed `100% left`, which implies a cap that does not exist. Now aligned.

### D4 — npm refresh runs under npm 11, verified under npm 10

`npm update` and `npm audit fix` fail on this lock with npm 10.9.8
(`Cannot read properties of null (reading 'edgesOut')`), including after a
clean `npm ci`. The refresh therefore ran under npm 11 and was verified with
npm 10 (the version the CI runner ships): `npm ci` installs the refreshed lock
and the suite stays at 400 passing. `package.json` ranges were not touched.

## Tasks (one file per commit)

| # | File | Change |
|---|---|---|
| 1 | `vscode-extension/package-lock.json` | refresh inside declared ranges, 9 → 0 advisories |
| 2 | `vscode-extension/src/historyPanel.test.ts` | prettier 3.9 reflow |
| 3 | `vscode-extension/src/types.ts` | optional `text_value` on `UsageItem` |
| 4 | `vscode-extension/src/api.ts` | wallet gate + literal rows |
| 5 | `vscode-extension/src/api.test.ts` | disabled / uncapped / newer shapes |
| 6 | `vscode-extension/src/statusBar.ts` | tooltip prints `text_value` |
| 7 | `vscode-extension/src/statusBar.test.ts` | tooltip literal row |
| 8-17 | `vscode-extension/l10n/bundle.l10n.*.json` (10) | `"Not enabled"` |
| 18 | `src/kimi_code_usage/providers/kimi.py` | same gate as the extension |
| 19 | `tests/test_provider_kimi.py` | flag, balance, and the disabled cases |
| 20 | this plan | record |

## Verification (measured, not inferred)

- Python: `346 passed` (341 → 346), `ruff check src tests` clean.
- Extension: `compile` 0, `lint` 0 with **47/47** warnings (the ratchet bit at
  49 during development and forced two real fixes: `balance == null` and
  `text_value != null`), `format:check` 0, `402 passed` (396 → 402).
- `npm audit`: 9 findings (4 high, 4 moderate, 1 low) → **0**.
- Live smoke against the real account (wallet `STATUS_DISABLED`), previously
  three rows:

  ```
  Kimi - Monthly Credits (web): 14.6/100.0 (15% used)
  Kimi - Weekly Usage: 16.0/100.0 (16% used)
  Kimi - 5h Limit: 0.0/100.0 (0% used)
  Kimi - Extra Usage: Not enabled
  ```

- `npm ci` under npm 10 installs the refreshed lock (CI parity).

## Deviations from the original round-2 sketch

- `(web)` marker dropped (D2) — the premise did not hold for the extension.
- The flag is used as an accept signal only; it does not change wording. There
  is no upstream rendering code to copy, and inventing a "no monthly cap"
  phrasing (plus currency formatting) would be speculative UI.
- Two extra files appeared: the prettier 3.9 reflow (forced by the dependency
  refresh, otherwise `format:check` fails) and the 10 l10n bundles (the new
  label must be translated everywhere, as the repo keeps all bundles in sync).

## Review follow-ups (fresh reviewer, whole branch)

A reviewer with no prior context re-ran every gate and found two defects this
branch introduced, plus three gaps in the new tests. All five are fixed:

1. **Important — the details picker disagreed with the tooltip.**
   `showDetails` (the command behind a status-bar click) still formatted every
   row as `<percent>% left`, so the same row read "Not enabled" in the tooltip
   and "100% left" in the picker. Fixed in `statusBar.ts`, pinned by a test.
2. **Important — active wallet without amounts diverged from Python.**
   The extension dropped the row; Python claimed `¥0.00`. Python now stays
   silent (no data is not zero), so both surfaces agree.
3. **Minor — the compact-bar assertion was vacuous.** `detectWindowType` was
   mocked to `'weekly'` for every label, so the text row really did enter the
   bar; only the word "Not enabled" was missing. The test now marks the row as
   `'other'` and asserts the label itself never appears.
4. **Minor — arrays passed as wallet objects.** `typeof [] === 'object'` let
   `{"booster_wallet": [1]}` produce a bogus row (Python skips it). Both
   `booster_wallet` and `balance` now reject arrays.
5. **Minor — the snake_case flag was untested.** `monthly_charge_limit_enabled`
   is now covered on both sides.

The reviewer could not falsify the lock refresh (every changed entry is dev-only,
`package.json` ranges untouched, `npm ci` works under npm 10), the 9 → 0 audit
drop, the one-file-per-commit mapping, the bilingual messages, or the l10n key
parity. Two pre-existing deviations were noted and left alone: `@types/vscode`
already exceeded `engines.vscode` before this branch, and the repo has no
packaging step.
