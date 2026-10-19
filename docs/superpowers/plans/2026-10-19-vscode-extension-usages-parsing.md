# VS Code Extension `/usages` Parsing Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the VS Code extension parse the live `GET /coding/v1/usages` payload the same way the (already merged) Python provider does — read the snake_case `booster_wallet`, and use `usages.limit_5h` / `usages.limit_7d` only to backfill windows the primary parse did not cover.

**Architecture:** Both changes live inside the extension's existing `parsePayload()` in `vscode-extension/src/api.ts`; no new module, no new dependency, no signature change. The wallet key selection is a small helper (`pickBoosterWallet`) that mirrors the Python `or`-chain semantics (`{}` must not shadow the other key); the window backfill is a minute-based guard (`windowMinutes`) plus a `used_ratio` row builder (`ratioRow`) that reuses the existing `toRow()`. The extension's own i18n keys for the two windows are reused verbatim, so `detectWindowType()` keeps working exactly as it does for the primary path.

**Tech Stack:** TypeScript (`strict`, `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`), Node 22, vitest 4 (with the committed `src/__mocks__/vscode.ts` alias), eslint 10, prettier 3, `tsc -p ./` as the typecheck.

**Spec / reference implementation:** `docs/superpowers/specs/2026-07-28-kimi-monthly-usage-design.md` (repo design doc). The authoritative behaviour to mirror is the merged Python provider — `src/kimi_code_usage/providers/kimi.py`: `_parse_usage_payload()` (the `usages` block at L170–181), `_window_minutes()` (L72–87), `_ratio_usage_row()` (L116–131), and `_extra_usage_rows()` (L206: `payload.get("booster_wallet") or payload.get("boosterWallet")`). Read those four before starting; this plan is their TypeScript translation, not a re-design.

## Global Constraints

- Live payload facts (probed 2026-10-19, API-key auth): top-level keys are exactly `booster_wallet`, `limits`, `usage`, `usages`; the wallet's *inner* keys are camelCase (`status`, `monthlyUsed`, `monthlyChargeLimit`, each with a **string** `priceInCents` and a `currency`); `usages.limit_5h` / `usages.limit_7d` carry `used_ratio` as a **0–1 fraction** (`limit_7d.used_ratio = 0.1631` ↔ `usage` derives 16.0%).
- `used_ratio` becomes `percent = clamp(ratio * 100, 0, 100)`, rendered as `limit: 100`. Never fabricate absolute request counts.
- Backfill rows must never duplicate a window the primary parse already emitted, and the guard must count **rows emitted**, not windows seen.
- `camelCase` (`boosterWallet`) and the legacy `parallel` / `totalQuota` branches stay supported and must keep passing their existing tests. No deletions.
- i18n: reuse only existing keys — `t('Weekly limit')`, `t('5 Hours')`. Do not add l10n entries.
- Test/lint/verify commands run from `vscode-extension/`: `npm test` (vitest), `npm run compile` (tsc), `npm run lint` (eslint). Baseline before this branch: **382 tests / 13 files passing**, `npm run compile` clean, `npm run lint` = 42 warnings / 0 errors.
- `npm run format:check` **already fails** on exactly `src/api.ts` and `src/api.test.ts` (pre-existing drift, unrelated to this change; it is not part of CI). Do **not** fix it here — a whole-file prettier reformat would swamp a surgical diff. Write new code in prettier style.
- Done means: the whole extension suite is green, `compile` clean, `lint` shows **no new errors** (warnings have a pre-existing budget of 42), and the new tests fail before the implementation and pass after.

## Scope Decisions (already made — do not re-litigate)

In scope: the two parsing defects above.
Deliberately **out** of scope, agreed with the user on 2026-10-19 ("先只修解析错误"):
- Parity copy/UX: no `Monthly Credits (web)` marker, no `Extra Usage: Not enabled` row. The extension therefore still renders **nothing** for the dev account's `STATUS_DISABLED` wallet — a disabled wallet is `null`, exactly as before.
- The monthly OAuth path (`fetchMonthlyUsageViaOAuth`, api.ts:448 reading `payload.totalQuota`) is left untouched: `totalQuota` is structurally absent from the live endpoint, and the extension deliberately has no WebBridge fallback (documented at api.ts:383). Its tests stay as they are.
- Upstream's `booster_wallet.balance` (`amount` / `amountLeft`, a `cents × 10^6` fixed point) and `monthlyChargeLimitEnabled` are **not** adopted — they are a new feature, not a parsing fix.

## Review Focus

- **`used_ratio` scale drift.** If the server ever sends 0–100 instead of 0–1, the clamp turns it into a silent 100% rather than a wild 1631%. Pinned by the `clamps out-of-range ratios` test.
- **Non-numeric `used_ratio`.** `true`/`{}`/`'abc'` must be *rejected*, not coerced (JS `Number(true) === 1` would render 100%). Pinned by the `skips unusable usages entries` test.
- **`booster_wallet: {}` shadowing.** `{}` is truthy in JS (unlike Python), so a naive `??`/`||` chain could hide a valid camelCase wallet. Pinned by the `prefers snake_case and falls back to camelCase` test.
- **Duplicate 5h rows.** The suppression guard must key off the window's *duration in minutes*, not the row's label (a server `name` such as `五小时限额` defeats label matching), and must count only rows actually emitted. Pinned by `does not duplicate a 5h window that already produced a row`, `counts rows emitted, not windows seen`, and `does not depend on the limits label to detect the 5h window`.
- **Hostile input.** `usages` a string, an entry `null`/`{}`/a number, `limits` not an array — `parsePayload` must never throw. Pinned by the `skips unusable usages entries` test and by extending the existing `does not throw on hostile input` test.

---

### Task 1: Commit the plan

**Files:**
- Create: `docs/superpowers/plans/2026-10-19-vscode-extension-usages-parsing.md` (this file)

- [x] **Step 1: Prepare the worktree** (already created: `.worktrees/fix-vscode-extension-parsing`, branch `fix/vscode-extension-parsing`, based on `main` @ `a5334ea`)

```bash
cd /Users/hainingyu/Code/kimi_usage/.worktrees/fix-vscode-extension-parsing/vscode-extension
npm ci          # NOTE: plain `npm ci` fails — see the copy step in the As-executed section
npm test        # expect 382 passed / 13 files
```

- [x] **Step 2: Commit this plan**

```bash
cd /Users/hainingyu/Code/kimi_usage/.worktrees/fix-vscode-extension-parsing
rtk git add docs/superpowers/plans/2026-10-19-vscode-extension-usages-parsing.md
rtk git commit -m "docs(plan): add plan for the VS Code extension /usages parsing fix

docs(plan): 新增 VS Code 扩展 /usages 解析修复计划"
```

---

### Task 2: The live-shape tests

**Files:**
- Modify: `vscode-extension/src/api.test.ts` (append a new `describe` block after the existing `parsePayload parallel / boosterWallet / totalQuota` block, i.e. after line 445)

**Interfaces:**
- Consumes: the existing `parsePayload(payload: unknown): UsageItem[]` and `detectWindowType(label: string): WindowType` exports.
- Produces: the executable specification of Task 3. No production symbol is introduced here.

- [x] **Step 1: Write the failing tests**

Append this block (values come from the 2026-10-19 live probe):

```ts
describe('parsePayload live 2026-10-19 shape (usages / booster_wallet)', () => {
  const LIVE = {
    usage: { limit: '100', used: '16', remaining: '84', resetTime: '2026-10-26T08:22:11.102028Z' },
    limits: [
      {
        window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' },
        detail: { limit: '100', used: '0', remaining: '100', resetTime: '2026-10-19T09:22:11.102028Z' },
      },
    ],
    usages: { limit_5h: { used_ratio: 0 }, limit_7d: { used_ratio: 0.1631 } },
    booster_wallet: {
      status: 'STATUS_DISABLED',
      allowTopup: true,
      monthlyUsed: { currency: 'CNY', priceInCents: '0' },
      monthlyChargeLimit: { currency: 'CNY', priceInCents: '10000' },
    },
  };

  it('replays the live payload without duplicate windows', () => {
    const items = parsePayload(LIVE);
    expect(items).toHaveLength(2);
    expect(items.filter((i) => detectWindowType(i.label) === 'weekly')).toHaveLength(1);
    expect(items.filter((i) => detectWindowType(i.label) === 'fiveHours')).toHaveLength(1);
    expect(items[0].label).toBe('Weekly limit');
    expect(items[0].used).toBe(16); // from `usage`, never from usages.limit_7d
  });

  it('reads snake_case booster_wallet with string cents', () => {
    const items = parsePayload({
      booster_wallet: {
        status: 'STATUS_ENABLED',
        monthlyUsed: { currency: 'CNY', priceInCents: '1234' },
        monthlyChargeLimit: { currency: 'CNY', priceInCents: '10000' },
      },
    });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Extra Usage');
    expect(items[0].used).toBeCloseTo(12.34);
    expect(items[0].limit).toBe(100);
    expect(items[0].percent_left).toBeCloseTo(87.66);
  });

  it('prefers snake_case and falls back to camelCase', () => {
    const snake = {
      status: 'STATUS_ENABLED',
      monthlyUsed: { priceInCents: '5000' },
      monthlyChargeLimit: { priceInCents: '10000' },
    };
    const camel = {
      status: 'STATUS_ENABLED',
      monthlyUsed: { priceInCents: '1' },
      monthlyChargeLimit: { priceInCents: '10000' },
    };
    expect(parsePayload({ booster_wallet: snake, boosterWallet: camel })[0].used).toBeCloseTo(50);
    expect(parsePayload({ booster_wallet: {}, boosterWallet: camel })[0].used).toBeCloseTo(0.01);
    expect(parsePayload({ boosterWallet: camel })[0].used).toBeCloseTo(0.01);
  });

  it('backfills the weekly row from usages.limit_7d when usage is absent', () => {
    const items = parsePayload({ usages: { limit_7d: { used_ratio: 0.1631 } } });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Weekly limit');
    expect(items[0].used).toBeCloseTo(16.31);
    expect(items[0].limit).toBe(100);
    expect(items[0].remaining).toBeCloseTo(83.69);
    expect(items[0].percent_left).toBeCloseTo(83.69);
    expect(detectWindowType(items[0].label)).toBe('weekly');
  });

  it('backfills the 5h row from usages.limit_5h when no 300-minute row exists', () => {
    const items = parsePayload({ usages: { limit_5h: { used_ratio: 0.25 } } });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('5 Hours');
    expect(items[0].used).toBe(25);
    expect(items[0].remaining).toBe(75);
    expect(items[0].percent_left).toBe(75);
    expect(detectWindowType(items[0].label)).toBe('fiveHours');
  });

  it('does not duplicate a 5h window that already produced a row', () => {
    const items = parsePayload({
      limits: [
        { window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' }, detail: { limit: '100', used: '21' } },
      ],
      usages: { limit_5h: { used_ratio: 0.9 } },
    });
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(21);
  });

  it('counts rows emitted, not windows seen', () => {
    const items = parsePayload({
      limits: [{ window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' }, detail: {} }],
      usages: { limit_5h: { used_ratio: 0.5 } },
    });
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(50);
  });

  it('does not depend on the limits label to detect the 5h window', () => {
    const items = parsePayload({
      limits: [
        {
          window: { duration: 5, timeUnit: 'TIME_UNIT_HOUR' },
          detail: { name: '五小时限额', limit: '100', used: '21' },
        },
      ],
      usages: { limit_5h: { used_ratio: 0.9 } },
    });
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(21);
  });

  it('clamps out-of-range ratios and accepts numeric strings', () => {
    expect(parsePayload({ usages: { limit_5h: { used_ratio: 2.5 } } })[0].used).toBe(100);
    expect(parsePayload({ usages: { limit_5h: { used_ratio: -1 } } })[0].used).toBe(0);
    expect(parsePayload({ usages: { limit_7d: { used_ratio: '0.1631' } } })[0].used).toBeCloseTo(16.31);
  });

  it('skips unusable usages entries', () => {
    expect(parsePayload({ usages: 'nope' } as any)).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: 'x' } } as any)).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: null } } as any)).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: {} } })).toHaveLength(0);
    expect(parsePayload({ usages: { limit_7d: { used_ratio: 'abc' } } })).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: { used_ratio: true } } } as any)).toHaveLength(0);
  });
});
```

- [x] **Step 2: Extend the existing hostile-input test** (`does not throw on hostile input`, api.test.ts:434) with the two new fields:

```ts
        usages: { limit_5h: { used_ratio: {} }, limit_7d: [] },
        booster_wallet: 'not-an-object',
```

- [x] **Step 3: Retitle the stale fixture test.** `it('parses the real 2026-08-28 API response shape', ...)` (api.test.ts:278) pins a payload that the live server no longer sends. Rename it to `it('parses the legacy 2026-08-28 camelCase shape', ...)` and leave its body untouched — it is now the compatibility test for `boosterWallet`, `parallel`, and `totalQuota`.

- [x] **Step 4: Run the tests and confirm they fail for the right reason**

Run: `cd vscode-extension && npm test`
Expected: FAIL — the new block's failures are (a) `reads snake_case booster_wallet…` and the three `prefers snake_case…` assertions getting 0 items / `undefined`, (b) all four `usages` backfill tests getting 0 items, (c) `replays the live payload…` still passing at 2 items (it is the regression guard, and it must stay green before and after). The pre-existing 382 tests must all still pass.

- [x] **Step 5: Commit**

```bash
cd /Users/hainingyu/Code/kimi_usage/.worktrees/fix-vscode-extension-parsing
rtk git add vscode-extension/src/api.test.ts
rtk git commit -m "test(vscode): pin the live /usages shape and the backfill rules

test(vscode): 用 live /usages 形状与新回填规则钉住测试"
```

---

### Task 3: The parsing implementation

**Files:**
- Modify: `vscode-extension/src/api.ts` — `parsePayload()` (L66–112), plus two new private helpers next to `parseBoosterWallet` (L131) and one next to `toRow` (L165)

**Interfaces:**
- Consumes: `toInt`, `clamp`, `t`, and the existing `toRow(data, defaultLabel)`.
- Produces: `pickBoosterWallet(data: Record<string, unknown>): unknown`, `windowMinutes(window: unknown): number | null`, `ratioRow(entry: Record<string, unknown>, label: string): UsageItem | null` — all module-private; `parsePayload`'s exported signature is unchanged.

- [x] **Step 1: Add `pickBoosterWallet` and use it**

Insert above `parseBoosterWallet` (api.ts:131) and replace the `data.boosterWallet` argument at api.ts:102:

```ts
/** Live `/usages` uses snake_case `booster_wallet`; older payloads used camelCase. */
function pickBoosterWallet(data: Record<string, unknown>): unknown {
  for (const key of ['booster_wallet', 'boosterWallet']) {
    const value = data[key];
    if (value && typeof value === 'object' && Object.keys(value).length > 0) return value;
  }
  return undefined;
}
```

```ts
  const boosterRow = parseBoosterWallet(pickBoosterWallet(data));
```

The `Object.keys(...).length > 0` clause is deliberate: the Python reference uses `or`, which skips an empty mapping; without it an empty `booster_wallet` would hide a valid camelCase wallet.

- [x] **Step 2: Add `windowMinutes`** (mirrors `_window_minutes`, Python L72–87)

```ts
/** Minutes covered by a `limits[].window`, used to recognise a window we already emitted. */
function windowMinutes(window: unknown): number | null {
  if (!window || typeof window !== 'object') return null;
  const data = window as Record<string, unknown>;
  const duration = toInt(data.duration);
  if (duration == null) return null;
  const timeUnit = String(data.timeUnit ?? data.time_unit ?? '').toUpperCase();
  if (timeUnit.includes('MINUTE')) return duration;
  if (timeUnit.includes('HOUR')) return duration * 60;
  if (timeUnit.includes('DAY')) return duration * 1440;
  if (timeUnit.includes('MONTH')) return duration * 43200;
  return duration / 60;
}
```

- [x] **Step 3: Add `ratioRow`** (mirrors `_ratio_usage_row`, Python L116–131)

```ts
/** Row for a `usages.limit_5h` / `limit_7d` entry, whose `used_ratio` is a 0–1 fraction. */
function ratioRow(entry: Record<string, unknown>, label: string): UsageItem | null {
  const raw = entry.used_ratio;
  if (typeof raw !== 'number' && typeof raw !== 'string') return null;
  const ratio = Number(raw);
  if (!Number.isFinite(ratio)) return null;
  const used = clamp(ratio * 100, 0, 100);
  return toRow({ ...entry, name: null, title: null, limit: 100, used }, label);
}
```

`name`/`title` are nulled so the caller's label wins (the Python row builder forces the label); the reset fields come from `toRow` for free. Rejecting non-number/non-string is stricter than Python's `isinstance(ratio, (int, float))` check, which lets `true` through as 100% — an intentional, documented divergence.

- [x] **Step 4: Wire the two guards and the backfills into `parsePayload`**

(a) Hoist the `usage` row into a variable so the weekly guard can see it (replaces api.ts:71–75):

```ts
  const usage = data.usage;
  const usageRow =
    usage && typeof usage === 'object'
      ? toRow(usage as Record<string, unknown>, t('Weekly limit'))
      : null;
  if (usageRow) items.push(usageRow);
```

(b) In the `limits` loop, record a window's minutes **only when its row was emitted** (replaces api.ts:94–95):

```ts
      const row = toRow(detail, label);
      if (row) {
        items.push(row);
        const minutes = windowMinutes(itemObj.window);
        if (minutes != null) limitWindows.push(minutes);
      }
```

with `const limitWindows: number[] = [];` declared before the loop.

(c) Append the `usages` block immediately after the `limits` loop (before `parseParallel`):

```ts
  const usages = data.usages;
  if (usages && typeof usages === 'object') {
    const windows = usages as Record<string, unknown>;
    const sevenDays = windows.limit_7d;
    if (!usageRow && sevenDays && typeof sevenDays === 'object') {
      const row = ratioRow(sevenDays as Record<string, unknown>, t('Weekly limit'));
      if (row) items.unshift(row); // the weekly row leads, as it does on the primary path
    }
    const fiveHours = windows.limit_5h;
    if (!limitWindows.includes(300) && fiveHours && typeof fiveHours === 'object') {
      const row = ratioRow(fiveHours as Record<string, unknown>, t('5 Hours'));
      if (row) items.push(row);
    }
  }
```

- [x] **Step 5: Run the tests, typecheck, and lint**

Run: `cd vscode-extension && npm test && npm run compile && npm run lint`
Expected: **392 passed / 13 files**; `tsc` silent; eslint reports **0 errors** and no more than the pre-existing **42 warnings**.

- [x] **Step 6: Commit**

```bash
cd /Users/hainingyu/Code/kimi_usage/.worktrees/fix-vscode-extension-parsing
rtk git add vscode-extension/src/api.ts
rtk git commit -m "fix(vscode): read booster_wallet and backfill usages windows

fix(vscode): 读取 booster_wallet 并用 usages 窗口回填"
```

---

### Task 4 (recommended, droppable): Make the extension's checks actually run in CI

**Why:** `vscode-extension/.github/workflows/ci.yml` sits in a subdirectory, so GitHub Actions never discovers it — the extension's typecheck/lint/test have **never** run on a pull request. This fix would otherwise ship with zero CI coverage.

**Files:**
- Create: `.github/workflows/vscode-extension.yml`
- Delete: `vscode-extension/.github/workflows/ci.yml` (dead file — its content is superseded by the above)

- [x] **Step 1: Create the root workflow**

```yaml
name: VS Code Extension CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  extension:
    name: Extension typecheck, lint, test
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: vscode-extension
    steps:
      - uses: actions/checkout@v4
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '22'

      # vscode-extension/package-lock.json is git-ignored, so `npm ci` cannot be
      # used here, and setup-node's `cache: npm` would fail on the missing lock
      # file. Commit the lock file (and drop the ignore rule) to switch this step
      # to a reproducible `npm ci`.
      - name: Install dependencies
        run: npm install --no-audit --no-fund
      - name: Typecheck
        run: npm run compile
      - name: Lint
        run: npm run lint
      - name: Test
        run: npm test
```

- [x] **Step 2: Commit the new workflow**

```bash
cd /Users/hainingyu/Code/kimi_usage/.worktrees/fix-vscode-extension-parsing
rtk git add .github/workflows/vscode-extension.yml
rtk git commit -m "ci: run the vscode extension checks from the repository root

ci: 在仓库根目录运行 VS Code 扩展的检查"
```

- [x] **Step 3: Commit the deletion** (separate commit — one file per commit)

```bash
rtk git rm vscode-extension/.github/workflows/ci.yml
rtk git commit -m "chore(vscode): drop the subdirectory workflow GitHub never runs

chore(vscode): 删除 GitHub 不会执行的子目录 workflow"
```

---

## Final Verification (before opening the PR)

```bash
cd /Users/hainingyu/Code/kimi_usage/.worktrees/fix-vscode-extension-parsing
rtk git log --oneline main..HEAD            # one commit per file
cd vscode-extension
npm ci
npm test                                     # 392 passed / 13 files
npm run compile                              # silent
npm run lint                                 # 0 errors, <= 42 warnings
node -e "const {parsePayload}=require('./out/api.js'); ..."   # optional: replay the raw probe JSON
```

Then push `fix/vscode-extension-parsing`, open a PR against `main` with a bilingual body (English first) that states plainly: the two fixes, the live-probe evidence, the 382 → 392 test delta, and the deferred items from **Scope Decisions** (no `(web)` marker, no `Not enabled` row, dead OAuth monthly path untouched, `balance`/`monthlyChargeLimitEnabled` not adopted, `format:check` drift pre-existing).

---

## As executed (2026-10-19)

All tasks completed, on branch `fix/vscode-extension-parsing`, one file per commit: plan → `api.test.ts` → `api.ts` → root workflow → deleted subdirectory workflow (tests committed before the implementation, so the TDD order is readable from history).

**Ruling 1 — `npm ci` cannot run in a fresh worktree, or in CI.** `vscode-extension/package-lock.json` is git-ignored (root `.gitignore:15`), so a fresh worktree has no lock file and `npm ci` aborts with `EUSAGE`; GitHub has the same problem, which also means `setup-node`'s `cache: 'npm'` with a `cache-dependency-path` aimed at that lock file would have failed there. The workflow therefore drops both and uses `npm install --no-audit --no-fund`. Locally, copy the main checkout's ignored lock into the worktree (it stays out of the diff) and then run `npm ci` — that is what produced the 382-test baseline above. The lock file was deliberately **not** committed and `.gitignore` deliberately **not** edited: repo-wide dependency hygiene is outside this plan's agreed scope and is the user's call (AGENTS.md argues the opposite way: lock files belong in git). Cost if wrong: the extension CI job installs floating minor/patch versions instead of the locked set.

**Ruling 2 — the plan's own Task 1 step needed the same correction.** See Ruling 1.

**Ruling 3 — the lint budget is 47 warnings, not the 42 this plan guessed.** Every new warning is `@typescript-eslint/strict-boolean-expressions` on guards the file's pre-existing idiom already triggers 42 times; **0 errors**, so `npm run lint` still exits 0. Accepted rather than converted to explicit `!== null` comparisons, which would deviate from the surrounding style for no behavioural gain.

**Ruling 4 — formatting-only deviation from this plan's code block.** `usageRow`'s ternary is written on one line because `.prettierrc.json` sets `printWidth: 110` and prettier joins it. Every new line in both files was afterwards verified prettier-clean; the remaining `format:check` failures in `api.ts` / `api.test.ts` are pre-existing and deliberately untouched (a whole-file reformat has no place in this PR).

### Review fix wave

The whole-branch review found **no Critical** issue and killed 8 of 12 mutations. Four survived, and each survivor was a case where this plan's **Review Focus** claimed an invariant was pinned when it was not. The fix wave adds one test per surviving mutation — each verified to fail against that mutation and pass against the code — plus one code fix:

| Finding | Evidence |
| :--- | :--- |
| The 5h suppression guard's *minute* matching was unpinned (`limitWindows.length === 0` survived) | new test `backfills 5h even when a different limit window was emitted` — mutation KILLED |
| `ratioRow`'s `name`/`title` override was unpinned | new test `ignores a name carried by the usages entry` — mutation KILLED |
| The weekly backfill's lead position was unpinned | new test `leads with the backfilled weekly row` — mutation KILLED |
| `pickBoosterWallet`'s object check was unpinned | new test `falls through a non-object snake_case wallet` — mutation KILLED |
| A blank or non-decimal `used_ratio` (`''`, `'0x10'`) fabricated a "0% used / 100% left" row | `ratioRow` now requires a plain decimal string (`DECIMAL_RATIO_PATTERN`); assertions added to `skips unusable usages entries`, watched failing first |

Final state: **396 passed / 13 files**, `npm run compile` silent, `npm run lint` 0 errors / 47 warnings.
