# Round 3 — a real dependency gate, Dependabot, and the fastmcp/mcp majors

Date: 2026-10-20
Base: `main` @ `3897a47` (merge of PR #22, round 2)

Two PRs, deliberately:

- **part 1** (`#23`): replace the inert `uv audit` step, add `dependabot.yml`;
- **part 2** (this branch): upgrade `fastmcp` 3 → 4 and `mcp` 1 → 2, guarded by a
  new real-protocol smoke test.

## Why

Round 1 found that `.github/workflows/ci.yml` ran `uv audit || true`, and that
`uv audit` is not a subcommand of uv 0.9.17 — the step failed on every run and
`|| true` hid it. Nothing was ever audited. Dependency drift also arrived only
when someone happened to look at the alerts: 56 pip advisories and an untracked
npm lock had accumulated before round 1.

Round 1 also deferred the two majors (`fastmcp` 3 → 4, `mcp` 1 → 2) explicitly,
because every MCP test mocks the transport — the suite could stay green while
the published `kimi-mcp` entry point stopped working.

## Decisions

### D1 — audit with `pip-audit`, on the frozen lock, as a hard gate

```
uv export --frozen --no-emit-project --format requirements-txt --no-hashes > "$RUNNER_TEMP/requirements.txt"
uvx pip-audit@2.10.1 --disable-pip --no-deps -r "$RUNNER_TEMP/requirements.txt" --progress-spinner off
```

- pip-audit's default `-r` path builds a temporary venv and dies with `SIGABRT`
  (`ensurepip`) on uv-managed interpreters — measured locally. `--disable-pip
  --no-deps` audits the pins without any venv.
- pip-audit is pinned (`@2.10.1`): an unpinned tool can break the gate overnight.
- Hard gate, not `|| true`. Measured both ways: current lock exits 0 with "No
  known vulnerabilities found"; `aiohttp==3.8.0` exits 1.
- It audits the same source Dependabot reads (`uv.lock`), so the two agree.

### D2 — Dependabot: weekly, grouped minors/patches, majors alone

`uv` (root), `npm` (`vscode-extension`), `github-actions`. Minors and patches are
grouped per ecosystem because they share a lockfile; majors stay separate
because they need their own verification — `fastmcp`/`mcp` are the proof.

### D3 — smoke first, then upgrade

The real-protocol test was written and **passed on the old versions**
(fastmcp 3.2.4 / mcp 1.30.0) before any version changed. It spawns
`python -m kimi_code_usage.mcp`, initializes a session, lists tools, and calls
one. The child gets a throwaway `HOME` and no provider credentials, so it never
reads the developer's config or contacts a provider.

Only after that baseline did the majors move.

### D4 — pin the `fastmcp` floor

`fastmcp>=0.1.0` allowed every major ever published. The floor is now the
version actually supported and tested (`>=4.1.1`).

## Result of the majors

**No application code change was required.** `FastMCP(...)`, `@mcp.tool()` and
`mcp.run()` kept their signatures. The only fallout was in the new smoke test:
mcp 2 renames `InitializeResult.serverInfo` → `server_info` (deprecated field),
which the test now uses, verified under `-W error::DeprecationWarning`.

Dependency shape changed: fastmcp 4 pulls `fastmcp-slim[client,server]`, which
brings `mcp-types`, `httpx2-jsfetch` and `truststore`; `mcp` 2 splits its types
into `mcp-types`.

## Verification (measured)

| Check | Result |
|---|---|
| Python suite on fastmcp 4.1.1 / mcp 2.3.0 | **347 passed** (346 + the new smoke) |
| Coverage | 95% (gate: 85%) |
| `ruff check src tests`, `mypy src/` | clean |
| `uv lock --check` | resolves, no drift |
| Real `kimi-mcp` entry point over stdio (manual) | server `Kimi Code Usage`, tools `get_kimi_usage`/`get_usage`, call returns text |
| pip-audit gate (part 1) | lock 0, `aiohttp==3.8.0` exit 1; ran for real in CI run 39360560161 |

## Not done, on purpose

- Bandit and mypy remain soft (`|| true`) — out of scope here; unlike the audit
  step they do run and do print findings.
- No `vsce package` step exists, so `@types/vscode` staying ahead of
  `engines.vscode` (pre-existing) has no runtime effect today.
- The version mismatch between `pyproject.toml` (0.1.6) and the extension's
  `package.json` (0.1.9) is untouched — it needs a release decision, not a
  dependency change.
