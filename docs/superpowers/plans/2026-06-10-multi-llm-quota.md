# Multi-LLM Quota Integration Implementation Plan

**Goal:** Extend `kimi-code-usage` to query OpenAI, Anthropic, and OpenRouter quotas alongside Kimi in CLI and MCP server, maintaining 100.00% test coverage.

---

## Task 1: Setup ConfigResolver and Provider Models

**Files:**
- Create: `src/kimi_code_usage/config.py`
- Create: `src/kimi_code_usage/providers/__init__.py`

- [ ] **Step 1: Create `src/kimi_code_usage/config.py`**
  Implement loading settings from both `~/.kimi-usage/config.json` (or customizable config path) and environment variables (`KIMI_API_KEY`, `OPENAI_API_KEY`, etc.).

- [ ] **Step 2: Create `src/kimi_code_usage/providers/__init__.py`**
  Define `ProviderUsage` dataclass and dispatcher logic.

- [ ] **Step 3: Create tests for `config.py`**
  Write tests in `tests/test_config.py` covering env load, config JSON load, empty config fallback, and custom config paths.

- [ ] **Step 4: Verify test coverage**
  Ensure test coverage for `config.py` is 100.00%.

---

## Task 2: Extract Kimi Provider Logic

**Files:**
- Create: `src/kimi_code_usage/providers/kimi.py`

- [ ] **Step 1: Implement `src/kimi_code_usage/providers/kimi.py`**
  Extract the existing Kimi fetcher logic from `main.py` into this file, converting the return values into `ProviderUsage` models.

- [ ] **Step 2: Create tests for `kimi.py`**
  Write `tests/test_provider_kimi.py` matching the original Kimi usage test cases.

- [ ] **Step 3: Verify test coverage**
  Ensure test coverage for Kimi provider is 100.00%.

---

## Task 3: Implement OpenAI, Anthropic, and OpenRouter Fetchers

**Files:**
- Create: `src/kimi_code_usage/providers/openai.py`
- Create: `src/kimi_code_usage/providers/anthropic.py`
- Create: `src/kimi_code_usage/providers/openrouter.py`

- [ ] **Step 1: Implement OpenAI Fetcher**
  Fetch organizations completions usage and costs. Gracefully handle 401/403 admin key errors.

- [ ] **Step 2: Implement Anthropic Fetcher**
  Fetch from `api.anthropic.com/api/oauth/usage`. Fallback to message about API key restrictions if the key format isn't OAuth.

- [ ] **Step 3: Implement OpenRouter Fetcher**
  Fetch auth key limits and usage from `openrouter.ai/api/v1/auth/key`.

- [ ] **Step 4: Create Tests for Providers**
  Write tests in `tests/test_provider_openai.py`, `tests/test_provider_anthropic.py`, and `tests/test_provider_openrouter.py` mocking their respective API calls.

- [ ] **Step 5: Verify test coverage**
  Ensure all provider modules have 100.00% test coverage.

---

## Task 4: Refactor CLI main entry

**Files:**
- Modify: `src/kimi_code_usage/main.py`

- [ ] **Step 1: Adapt CLI args and dispatcher integration**
  Update `main.py` to use `ConfigResolver` and `dispatch_all()` from the registry. Support `--provider` option and custom `--config` path.

- [ ] **Step 2: Format Output UI**
  Design multi-card UI for rich formatting, and adapt `--json` and `--plain` modes.

- [ ] **Step 3: Update `tests/test_main.py`**
  Refactor existing tests to match the new Multi-Provider architecture and add tests for `--provider` filtering and multi-card layout rendering.

- [ ] **Step 4: Verify test coverage**
  Ensure `main.py` keeps 100.00% coverage.

---

## Task 5: Refactor MCP Server

**Files:**
- Modify: `src/kimi_code_usage/mcp.py`

- [ ] **Step 1: Refactor mcp tool**
  Expose `get_usage` with optional `provider` filter. Deprecate or alias `get_kimi_usage` to maintain backward compatibility.

- [ ] **Step 2: Update `tests/test_mcp.py`**
  Adapt and expand tests to mock the new multi-provider response.

- [ ] **Step 3: Verify test coverage**
  Verify MCP server maintains 100.00% test coverage.

---

## Task 6: Final Integration & Build Verification

- [ ] **Step 1: Build project**
  Verify pip packaging and entry points defined in `pyproject.toml`.

- [ ] **Step 2: Run all tests with coverage**
  `pytest --cov=src` to verify everything is 100.00% covered and no tests fail.
