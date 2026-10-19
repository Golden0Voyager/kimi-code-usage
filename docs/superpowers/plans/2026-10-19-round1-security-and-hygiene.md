# Round 1 — Dependency Security and VS Code Extension Hygiene

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the 2 critical / 16 high Dependabot alerts with a minimal-blast-radius lock upgrade, and close the two VS Code extension hygiene gaps that were explicitly deferred (lock file in git, formatting drift, lint-warning ratchet).

**Architecture:** No production code changes. Four independent workstreams land as one PR, each file in its own commit: (1) targeted `uv.lock` upgrade plus a raised floor on the one vulnerable *direct* dependency, (2) commit the extension's `package-lock.json` and switch its CI job back to `npm ci`, (3) a pure `prettier` reformat of the two drifted files, (4) a lint-warning cap of the current count.

**Tech Stack:** `uv` (Python lock), `npm`/`prettier`/`eslint` (VS Code extension), GitHub Actions.

**Spec:** This round has no standalone spec document. The agreed scope is the "轮 1" section of the review conversation that preceded this plan. The evidence it argues from — the 56 open Dependabot alerts, each with `first_patched_version` — is the JSON saved at `/private/var/folders/nm/84gtrjw50mbgh3mmqfb64w5m0000gp/T/opencode/dependabot.json`, and the two recon runs that produced the numbers below live at `/private/var/folders/nm/84gtrjw50mbgh3mmqfb64w5m0000gp/T/opencode/sec-recon/` (full `uv lock --upgrade`) and `.../sec-targeted/` (targeted upgrade).

## Global Constraints

- **One file per commit**, bilingual message (English block first, Chinese block second). Never bundle two files into one commit.
- Work only on `chore/round1-security-and-hygiene`; never push to `main`.
- **No test regression**: Python 341 passed, extension 396 passed, before and after.
- **No major-version jump**: `fastmcp` must stay `3.2.4`, `mcp` must stay `1.x` (`1.30.0`). Those majors are a separate round.
- Never read or modify `.env`, `secrets.json`, `cookies.json`. Any test credentials stay faked under `tmp_path`.
- Do not exceed this round: no monthly-parity UX work, no `fastmcp`/`mcp` major upgrade, do not touch the inert `uv audit || true` CI step, do not add `dependabot.yml`.
- Verified target state: **55 of 56** alerts cleared (the single survivor is a PyJWT `medium` with no upstream patch), **0** alerts remaining in-range, **13** of 104 packages changed (the lock resolves 107).

## Review Focus

Five inputs/conditions this plan implies but whose tests do not cover them, most likely first:

1. **Runtime behaviour of the upgraded libraries.** The Python suite is fully mocked, so it cannot prove that `aiohttp 3.14.5` / `cryptography 50.0.2` behave at runtime the way the code assumes. Mitigated by the bounded live smoke in Task 1 (a real CLI run) plus the fact that no major version moves.
2. **`npm ci` fetching from `registry.npmmirror.com`.** 169 of the lock's packages carry npmmirror URLs; a GitHub runner that cannot reach that host fails the job. Task 5 verifies this on the PR itself, with a documented fallback (rewrite `resolved` to `registry.npmjs.org`; the tarballs are mirror-identical so `integrity` stays valid).
3. **`--max-warnings 47` is bound to the locked eslint version.** It is only a stable number because Task 2 makes CI install from the lock. Any future `npm install` (floating) may legitimately change the count and turn the ratchet into a false red.
4. **The `.gitignore` negation must actually take effect, in both directions.** If it fails, the lock silently stays untracked (CI keeps using `npm install`); if it over-reaches, `node_modules` could become trackable. Task 2 checks both with `git check-ignore -v` and `git status`.
5. **The prettier rewrite must be formatting-only.** A reformat that changes behaviour would be invisible in review. Task 3 requires the diff to contain only line wrapping and trailing commas, and requires the suite to stay at 396.

---

### Task 1: Security — targeted lock upgrade

**Files:**
- Modify: `pyproject.toml` (the `aiohttp` dependency floor)
- Modify: `uv.lock`

**Interfaces:**
- Consumes: nothing.
- Produces: `uv.lock` at the resolved set `aiohttp 3.14.5`, `anyio 4.15.1`, `cryptography 50.0.2`, `idna 3.20`, `joserfc 1.7.7`, `mcp 1.30.0`, `multidict 7.1.0`, `pydantic-settings 2.16.0`, `pyjwt 2.15.1`, `python-multipart 0.0.32`, `starlette 1.9.0`, `typing-extensions 4.16.0`, `urllib3 2.8.0`, `yarl 1.25.1`.

- [ ] **Step 1: Raise the floor on the one vulnerable direct dependency**

In `pyproject.toml`, change the `aiohttp` requirement from `aiohttp>=3.8.0` to `aiohttp>=3.14.3`. `3.14.3` is the alert's `first_patched_version` — the minimum that actually protects a fresh install, not the newest available.

- [ ] **Step 2: Upgrade exactly those packages in the lock**

```bash
uv lock --upgrade-package aiohttp --upgrade-package anyio --upgrade-package cryptography \
  --upgrade-package joserfc --upgrade-package mcp --upgrade-package pyjwt \
  --upgrade-package python-multipart --upgrade-package starlette --upgrade-package urllib3 \
  --upgrade-package multidict --upgrade-package pydantic-settings --upgrade-package idna
```

- [ ] **Step 3: Verify the lock is consistent with `pyproject.toml`**

Run: `uv lock --check`
Expected: resolves and reports no inconsistency.

- [ ] **Step 4: Verify the suite**

Run: `uv run pytest -q tests/`
Expected: `341 passed`.

- [ ] **Step 5: Verify the alert math against the new lock**

Run the alert-vs-lock script (reads `.../dependabot.json`, compares every alert's `first_patched_version` with the version now in `uv.lock`).
Expected: `清除 55 / 56，仍在范围内 0，上游无修复 1` and the single survivor is `pyjwt 2.15.1 (NO-FIX)`.
Also confirm the diff touches **14** packages and that `fastmcp` is still `3.2.4` and `mcp` is `1.30.0`.

- [ ] **Step 6: Bounded live smoke (the suite is mocked)**

Run the real CLI once against the user's own configuration and assert the exit code and that a usage window row is rendered. Report only the shape and counts — never paste account identifiers (`email`, `plan`, tokens) into the transcript. Then check the upgraded imports resolve:

```bash
uv run python -c "import aiohttp, cryptography, jwt, starlette, urllib3, mcp; print(aiohttp.__version__, cryptography.__version__, jwt.__version__, starlette.__version__, urllib3.__version__, mcp.__version__ if hasattr(mcp,'__version__') else 'n/a')"
```

- [ ] **Step 7: Commit `pyproject.toml`**

```bash
git add pyproject.toml
git commit -m "fix(deps): require aiohttp >= 3.14.3 for the patched parser" -m "fix(deps): 要求 aiohttp >= 3.14.3，取用已修复的解析器"
```

- [ ] **Step 8: Commit `uv.lock`**

```bash
git add uv.lock
git commit -m "fix(deps): upgrade the vulnerable locked packages" -m "fix(deps): 升级锁定的受影响依赖"
```

---

### Task 2: Extension lock file in git

**Files:**
- Modify: `.gitignore`
- Create: `vscode-extension/package-lock.json` (113,858 bytes, copied from the main checkout)

**Interfaces:**
- Consumes: nothing.
- Produces: a tracked `vscode-extension/package-lock.json` on which Task 5's `npm ci` depends.

- [ ] **Step 1: Un-ignore the extension lock, surgically**

Append to `.gitignore`, under the existing `# Node.js` block:

```
# The VS Code extension's lock file is tracked so CI can install reproducibly.
!vscode-extension/package-lock.json
```

A negation rather than deleting line 15, so the other sub-projects' policy is untouched.

- [ ] **Step 2: Verify the negation works in both directions**

```bash
git check-ignore -v vscode-extension/package-lock.json; echo "exit=$?"   # expect: no output, exit=1
git check-ignore -v vscode-extension/node_modules 2>/dev/null && echo "node_modules 仍被忽略 ✓"
git status --porcelain vscode-extension/package-lock.json                # expect: "?? vscode-extension/package-lock.json"
```

- [ ] **Step 3: Commit `.gitignore`**

```bash
git add .gitignore
git commit -m "chore: track the VS Code extension's lock file" -m "chore: 让 VS Code 扩展的 lock 文件纳入版本控制"
```

- [ ] **Step 4: Commit the lock file**

```bash
git add vscode-extension/package-lock.json
git commit -m "chore(vscode): commit package-lock.json for reproducible installs" -m "chore(vscode): 提交 package-lock.json 以保证安装可复现"
```

- [ ] **Step 5: Prove `npm ci` works from scratch**

```bash
cd vscode-extension
rm -rf node_modules
npm ci
npm test
```

Expected: `npm ci` succeeds with no resolver involvement, `396 passed`.

---

### Task 3: Prettier drift

**Files:**
- Modify: `vscode-extension/src/api.ts` (2 hunks)
- Modify: `vscode-extension/src/api.test.ts` (5 hunks)

**Interfaces:**
- Consumes: nothing.
- Produces: a `src/` tree on which `prettier --check src` is clean, which Task 5's new CI step requires.

- [ ] **Step 1: Reformat exactly the two drifted files**

```bash
cd vscode-extension
npx prettier --write src/api.ts src/api.test.ts
```

Naming the two files (rather than `src`) guarantees nothing else moves.

- [ ] **Step 2: Verify the drift is gone and nothing else changed**

```bash
npx prettier --check src        # expect: "All matched files use Prettier code style!"
cd .. && git status --porcelain # expect: exactly those two files, " M"
```

- [ ] **Step 3: Verify the change is formatting-only**

Read `git diff` for both files. The only permitted non-whitespace differences are trailing commas and quote style — any token, operator, or statement difference is a bug and must be reverted.

- [ ] **Step 4: Verify behaviour is unchanged**

Run: `cd vscode-extension && npm test` → `396 passed`; `npm run lint` → `0 errors, 47 warnings`.

- [ ] **Step 5: Commit `api.ts`**

```bash
git add vscode-extension/src/api.ts
git commit -m "style(vscode): reflow api.ts to prettier's 110-column width" -m "style(vscode): 按 prettier 的 110 列宽重排 api.ts"
```

- [ ] **Step 6: Commit `api.test.ts`**

```bash
git add vscode-extension/src/api.test.ts
git commit -m "style(vscode): reflow api.test.ts to prettier's 110-column width" -m "style(vscode): 按 prettier 的 110 列宽重排 api.test.ts"
```

---

### Task 4: Lint-warning ratchet

**Files:**
- Modify: `vscode-extension/package.json` (the `lint` script, line 258)

**Interfaces:**
- Consumes: nothing.
- Produces: `npm run lint` that exits non-zero above 47 warnings, for Task 5's unchanged `Lint` step.

- [ ] **Step 1: Cap the current count**

Change `"lint": "eslint src"` to `"lint": "eslint src --max-warnings 47"`. A cap, not a target: it can only go down from here.

- [ ] **Step 2: Verify it passes at the current count**

Run: `cd vscode-extension && npm run lint; echo "exit=$?"`
Expected: `✖ 47 problems (0 errors, 47 warnings)`, `exit=0`.

- [ ] **Step 3: Verify the gate actually gates**

Create a throwaway file with a deliberate violation (e.g. `src/__ratchet_probe.ts` containing `export const x: any = 1;`), run `npm run lint`, confirm a non-zero exit and a warning above the cap, then delete the file and confirm `npm run lint` is green again. A ratchet nobody has seen bite is not a ratchet.

- [ ] **Step 4: Commit `package.json`**

```bash
git add vscode-extension/package.json
git commit -m "chore(vscode): cap lint warnings at the current 47" -m "chore(vscode): 将 lint 警告上限钉在当前的 47 条"
```

---

### Task 5: CI installs from the lock, and checks formatting

**Files:**
- Modify: `.github/workflows/vscode-extension.yml`

**Interfaces:**
- Consumes: the tracked lock from Task 2, the clean `src/` from Task 3, the capped `lint` script from Task 4.
- Produces: the final workflow behind the PR's green check.

- [ ] **Step 1: Rewrite the install path**

Remove the `Install a working npm` step and the `npm install --no-audit --no-fund` line. In its place:

```yaml
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'
          cache-dependency-path: vscode-extension/package-lock.json

      - name: Install dependencies
        run: |
          node --version
          npm --version
          npm ci
```

Replace the stale comment block with the reason `npm ci` is now correct: the lock is committed and `npm ci` never runs the resolver, so the Node 22 / npm 10.9.x `edgesOut` crash cannot trigger, and a floating `npm install` is no longer used.

- [ ] **Step 2: Add the formatting gate**

```yaml
      - name: Format check
        run: npm run format:check
```

Placed after `Lint`, before `Test`.

- [ ] **Step 3: Sanity-check the YAML and replay the job locally**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/vscode-extension.yml'))" && echo "YAML ok"
cd vscode-extension && npm ci && npm run compile && npm run lint && npm run format:check && npm test
```

Expected: YAML parses; the exact CI sequence exits 0 with `396 passed`.

- [ ] **Step 4: Commit the workflow**

```bash
git add .github/workflows/vscode-extension.yml
git commit -m "ci(vscode): install from the committed lock and gate formatting" -m "ci(vscode): 改为按已入库的 lock 安装，并加入格式门禁"
```

---

## Final verification (before the PR)

- [ ] `uv lock --check` clean; `uv run pytest -q tests/` → 341 passed.
- [ ] `cd vscode-extension && npm ci && npm run compile && npm run lint && npm run format:check && npm test` → all exit 0, 396 passed.
- [ ] `git log --format='%h %s' main..HEAD` shows one file per commit, no bundling.
- [ ] Alert math re-run against the committed `uv.lock`: 55/56 cleared, 0 in-range.
- [ ] Push the branch, open the PR against `main`, and confirm **both** CI workflows are green — this is also the check that a GitHub runner can fetch from `registry.npmmirror.com` (Review Focus 2).
- [ ] After review, ask before merging. Post-merge, re-query the Dependabot alerts API: the **pip** count must fall from 56 to 1. Do *not* expect the *total* to be 1 — see As executed §7.

---

## As executed (deviations from the steps above)

1. **`git check-ignore -v` on a negated pattern prints the pattern and exits 0.** Task 2 Step 2 expected no output and `exit=1`; git instead reports the negation match (`.gitignore:18:!vscode-extension/package-lock.json`) and exits 0. The check that actually discriminates is `git status --porcelain`, which showed `?? vscode-extension/package-lock.json` — untracked, hence no longer ignored — after which the commit added 3,367 lines.
2. **The upgrade touched 13 of 104 packages, not 14 of 108** (the lock resolves 107). `typing-extensions` did not move here; every other package matches the recon exactly. Clearing counts were as predicted: 55/56, 0 in-range, `{'critical': 2, 'high': 16, 'medium': 28, 'low': 9}`.
3. **The ratchet probe needs a rule this configuration actually enables.** A probe containing `export const x: any = 1` produced no warning at all, because `no-explicit-any` is off here. The probe that bites is an unused local (`no-unused-vars`): it took the run to `exit=1` with `ESLint found too many warnings (maximum: 47)`, and removing it returned `exit=0` / `47 problems (0 errors, 47 warnings)`.
4. **The job was renamed** to `Extension typecheck, lint, format, test`, so the check name matches what it now runs. It has deliberately *not* been made a required status check.
5. `npx prettier --write` reports "All files formatted correctly" even when it rewrote both files; the authoritative confirmations are `git status --porcelain` (exactly the two files) and `npx prettier --check src`.
6. The live smoke ran the real CLI on the upgraded runtime: `exit=0`, 57 output lines, three percentage rows, window labels `5h` / `Weekly` / `Monthly`. Only counts and labels were recorded, never account identifiers.
7. **Committing the lock expands the npm surface Dependabot scans, so the "56 → 1" expectation was wrong.** Dependabot currently sees only the extension's 13 direct `devDependencies` — there was no lock for it to read. With the lock tracked it scans the full 164-package tree, which `npm audit` reports as 9 findings (1 low, 4 moderate, 4 high): `vitest`, `@vitest/ui`, `@vitest/mocker`, `esbuild`, `postcss`, `brace-expansion`, `nanoid`, `source-map-js` — all dev-only tooling that never ships in the VSIX. Expected post-merge state: **pip 56 → 1, total ≈ 10**. Accepted, and queued as a follow-up `npm audit fix` under the new lock; the alternative — leaving the lock untracked — is exactly what made this job's install floating and non-reproducible to begin with.
8. **The `uv.lock` diff is larger than "13 packages" suggests** (670 insertions / 461 deletions): six blocks whose versions did *not* change (`httpx`, `py-key-value-aio`, `secretstorage`, `sse-starlette`, `watchfiles`, `kimi-code-usage`) and the top-level `resolution-markers` list were rewritten by marker propagation, plus the `aiohttp` specifier. The reviewer diffed those blocks body-by-body: faithful consequence, not noise.
9. **`cdn.npmmirror.com` reachability from a GitHub-hosted runner is the one thing not verifiable locally.** 169 of the lock's 219 `resolved` URLs point there, and `npm ci` honours them verbatim. The fallback is validated: the same tarball from both hosts is byte-identical, so rewriting the 169 hosts to `registry.npmjs.org` keeps every `integrity` hash valid. The PR's first CI run is the test.


