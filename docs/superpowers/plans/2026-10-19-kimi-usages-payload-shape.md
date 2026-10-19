# Kimi /usages 响应形状漂移修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修好 Kimi `/usages` 实际响应形状与解析代码之间的偏移（蛇形 `booster_wallet`、新字段 `usages.limit_5h/limit_7d`），并让"月度额度结构性来自网页桥"这一事实在失败时显式呈现。

**Architecture:** 只改 Kimi provider 的两个模块。`kimi.py` 负责 coding API 侧解析（新增蛇形键、`usages` 窗口回退解析、月度行失败消息拼装）；`kimi_membership.py` 负责月度来源（OAuth 探测返回失败原因、WebBridge 结果打来源标记）。**不改渲染层**（`main.py` / `server.py` / `mcp.py`），**不新增 `ProviderUsage` 字段**——把改动面锁在两个文件内。

**Tech Stack:** Python（aiohttp、dataclass）、pytest + pytest-asyncio、ruff、mypy。

**Spec:** 无独立 spec 文档。本计划依据 2026-10-19 的实测证据（下方 Evidence 段），并与既有设计文档 `docs/superpowers/specs/2026-07-28-kimi-monthly-usage-design.md` 保持一致（该文档已写明"月度额度由登录后的 membership 页面展示"，本批次进一步证明这是**结构性**的、不是 token 过期导致的偶然现象）。

---

## Evidence（2026-10-19 实测，实施时不得凭记忆改动这些常量）

**E1 — API Key 认证下 `GET https://api.kimi.com/coding/v1/usages` 的顶层字段恰好为：**

```
['booster_wallet', 'limits', 'usage', 'usages']
```

四种请求头变体（裸 `Authorization` / `+Accept: application/json` / `+X-Msh-Platform: kimi_code_cli` / `+X-Msh-Version`）返回**完全一致** → 与请求头无关，是服务端形状演进。
**没有** `totalQuota`、**没有** `parallel`、**没有** camelCase 的 `boosterWallet`。

**E2 — `used_ratio` 的量纲是 0–1 比例（不是 0–100）：**

| 来源 | 值 | 派生百分比 |
|---|---|---|
| `usages.limit_5h.used_ratio` | `0` | `limits[0]` 派生 = 0.0% |
| `usages.limit_7d.used_ratio` | `0.1631` | `usage` 派生 = 16.0% |

**E3 — `booster_wallet` 的字段类型：** `priceInCents` 是**字符串**（现 `_price_in_yuan` 用 `_to_int` 已能处理），带 `currency: 'CNY'`；本机账号 `status` 为 `'STATUS_DISABLED'`。

**E4 — 官方 CLI 侧（`MoonshotAI/kimi-code` 及其公开镜像）解析 `/usages` 只取 `usage`(周) + `limits` + `boosterWallet`，官方自身没有"月度池"概念。** `totalQuota` 仅见于 2026-07 的旧 fixture，且社区文档明确其为"月度冻结标志"（二元 exhausted/available），现已从 live 响应消失。

**E5 — 月度百分比只能从 `https://www.kimi.com/membership/subscription?tab=quota` 页面 DOM 取得**（即现有 WebBridge 路径）。因此 `fetch_monthly_usage_from_oauth()` 期望的 `totalQuota` 在 coding API 上**永远不会出现**，该函数恒返回 `None` → 月度恒回退到 WebBridge。**本批次不删除该路径**（用户选择保留），但必须把"为什么回退"显式化。

---

## Global Constraints

- Python 强制 Type Hints（PEP 484）。
- 质检链依 AGENTS.md：`ruff check` → `mypy`（软失败）→ `pytest --cov` → `coverage report`；`fail_under = 85`。
- **一文件一提交**；提交信息中英双语、英文块在前中文块在后；**未经用户同意不得 push**。
- **外科手术式修改**：只动下方列出的文件与函数；禁止顺手重构；**禁止删除未验证的既有分支**（`totalQuota` / `parallel` / `data[]` / camelCase 分支全部原样保留）。
- **全程不读写凭据文件**：不得读取或修改 `.env`、`~/.kimi-code/credentials/kimi-code.json`（测试一律用 `tmp_path` 伪造）。
- 工作区：`.worktrees/fix-kimi-usages-payload`，分支 `fix/kimi-usages-payload`，基线 **312 passed** / ruff clean。

## Review Focus（这些是本批次最容易出事、且最容易漏测的点）

1. **同源重复出行**：live 形状同时含 `usage`+`limits` 与 `usages`，回退解析必须**不产生重复的 5h/周条**。
2. **`used_ratio` 量纲**：必须 ×100（0–1→百分比），且 clamp 到 0–100（防越界比例产出 >100%）。
3. **`usages` 只有比例没有绝对数**：这类行必须 `limit=100`、`unit="%"`，不得伪装成请求计数。
4. **月度失败消息必须同时给出两侧原因**：此前 OAuth 失败被 `except Exception: pass` 静默吞掉，只剩 WebBridge 一侧。
5. **既有 camelCase 形状零回归**：`boosterWallet` / `totalQuota` / `parallel` / `data[]` 行为与现有测试断言逐字保持。

---

### Task 0: 隔离工作区

- [x] **Step 1: 建立 worktree（已完成）**

```bash
cd /Users/hainingyu/Code/kimi_usage
rtk git pull --ff-only origin main
rtk proxy git worktree add .worktrees/fix-kimi-usages-payload -b fix/kimi-usages-payload main
```

- [x] **Step 2: 验证干净基线（已完成）**

Run: `uv run ruff check && uv run pytest -q`
Expected: `All checks passed!` + `312 passed`

---

### Task 1: 用测试钉住 `booster_wallet`（蛇形键）

**Files:**
- Test: `tests/test_provider_kimi.py`（追加到 `# -- _extra_usage_rows --` 段内）

**Interfaces:**
- Consumes: `_extra_usage_rows(payload: Mapping[str, Any], *, lang_zh: bool) -> list[ProviderUsage]`（现状签名不变）
- Produces: 无新公开接口（纯行为修复）

- [ ] **Step 1: 写失败测试**

```python
def test_extra_usage_rows_reads_snake_case_booster_wallet():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    # live 形状（E1/E3）：蛇形 key，priceInCents 是字符串
    payload = {
        "booster_wallet": {
            "status": "STATUS_DISABLED",
            "monthlyUsed": {"currency": "CNY", "priceInCents": "1234"},
            "monthlyChargeLimit": {"currency": "CNY", "priceInCents": "10000"},
        }
    }
    rows = _extra_usage_rows(payload, lang_zh=False)
    assert [r.label for r in rows] == ["Extra Usage"]
    assert rows[0].text_value == "Not enabled"


def test_extra_usage_rows_reads_snake_case_booster_wallet_enabled():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {
                "status": "STATUS_ENABLED",
                "monthlyUsed": {"currency": "CNY", "priceInCents": "1234"},
                "monthlyChargeLimit": {"currency": "CNY", "priceInCents": "10000"},
            }
        },
        lang_zh=False,
    )
    assert rows[0].label == "Extra Usage"
    assert rows[0].used == 12.34
    assert rows[0].limit == 100.0
    assert rows[0].unit == "¥"


def test_extra_usage_rows_snake_case_wins_over_camel_case():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {"status": "STATUS_DISABLED"},
            "boosterWallet": {"status": "STATUS_ENABLED"},
        },
        lang_zh=False,
    )
    assert rows[0].text_value == "Not enabled"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_provider_kimi.py -k "snake_case" -q`
Expected: FAIL（真实 key 未识别 → `rows == []`，`IndexError`）

---

### Task 2: 用测试钉住 `usages.limit_5h/limit_7d` 回退解析

**Files:**
- Test: `tests/test_provider_kimi.py`（追加到 `# -- _parse_usage_payload --` 段尾）

**Interfaces:**
- Consumes: `_parse_usage_payload(payload: Mapping[str, Any]) -> tuple[KimiRow | None, list[KimiRow]]`（现状签名不变）
- Produces: 同签名；`usages` 仅在 `usage`/`limits` 未覆盖该窗口时补行

- [ ] **Step 1: 写失败测试**

```python
def test_parse_usage_payload_falls_back_to_usages_windows():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    payload = {
        "usages": {
            "limit_5h": {"used_ratio": 0, "reset_time": "2026-10-19T15:00:00Z"},
            "limit_7d": {"used_ratio": 0.1631, "reset_time": "2026-10-26T00:00:00Z"},
        }
    }
    summary, limits = _parse_usage_payload(payload)

    assert summary is not None and summary.label == "Weekly Usage"
    assert summary.used == 16 and summary.limit == 100          # 0.1631 → 16%
    assert [r.label for r in limits] == ["5h Limit"]            # 周条已由 summary 覆盖，不重复
    assert limits[0].used == 0 and limits[0].limit == 100


def test_parse_usage_payload_ignores_usages_when_usage_and_limits_present():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    # live 形状（E1/E2）：两套来源同时存在 → 不得重复出行
    payload = {
        "usage": {"limit": "100", "remaining": "84", "resetTime": "2026-10-26T00:00:00Z"},
        "limits": [
            {
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "remaining": "100", "resetTime": "2026-10-19T15:00:00Z"},
            }
        ],
        "usages": {
            "limit_5h": {"used_ratio": 0, "reset_time": "2026-10-19T15:00:00Z"},
            "limit_7d": {"used_ratio": 0.1631, "reset_time": "2026-10-26T00:00:00Z"},
        },
    }
    summary, limits = _parse_usage_payload(payload)

    assert summary is not None and summary.label == "Weekly Usage"
    assert summary.used == 16 and summary.limit == 100
    assert [r.label for r in limits] == ["5h Limit"]            # 恰好一行，无重复
    assert limits[0].used == 0


def test_parse_usage_payload_usages_clamps_out_of_range_ratio():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    summary, limits = _parse_usage_payload({"usages": {"limit_7d": {"used_ratio": 3.5}}})

    assert summary is not None
    assert summary.used == 100 and summary.limit == 100


def test_parse_usage_payload_skips_usages_without_ratio():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    summary, limits = _parse_usage_payload(
        {"usages": {"limit_5h": {"reset_time": "2026-10-19T15:00:00Z"}, "limit_7d": "nope"}}
    )

    assert summary is None
    assert limits == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_provider_kimi.py -k "usages" -q`
Expected: FAIL（`usages` 目前完全未被解析 → `summary is None`）

---

### Task 3: 用测试钉住月度行的"来源标记 + 失败原因"

**Files:**
- Test: `tests/test_provider_kimi_membership.py`（改 2 个既有用例 + 追加新用例）
- Test: `tests/test_provider_kimi.py`（改 2 个既有月度调度用例 + 追加 1 个新用例）

**Interfaces:**
- Produces（Task 5 实现）：

  ```python
  def _load_token_state() -> tuple[str | None, str]          # (token, reason); reason == "" 表示成功
  def load_kimi_cli_access_token() -> str | None             # 保持原签名（= _load_token_state()[0]）
  async def fetch_monthly_usage_from_oauth(*, lang_zh: bool) -> tuple[ProviderUsage | None, str]
  async def fetch_monthly_usage_from_webbridge(*, lang_zh: bool) -> ProviderUsage  # 标签带来源标记
  ```

- [ ] **Step 1: 改造 `fetch_monthly_usage_from_oauth` 的既有用例（返回二元组）**

在 `tests/test_provider_kimi_membership.py` 中把

```python
        row = await fetch_monthly_usage_from_oauth(lang_zh=False)
```

改为

```python
        row, _reason = await fetch_monthly_usage_from_oauth(lang_zh=False)
```

（`test_fetch_monthly_usage_from_oauth_returns_total_quota` 与 `test_fetch_monthly_usage_from_oauth_falls_back_when_no_total_quota` 各一处；后者断言改为 `assert row is None`。）

- [ ] **Step 2: 追加 OAuth 失败原因用例**

```python
@pytest.mark.asyncio
async def test_fetch_monthly_usage_from_oauth_reports_missing_total_quota():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    # live 形状（E1）：coding API 永远没有 totalQuota
    cm.json = AsyncMock(return_value={"usage": {"limit": "100", "remaining": "84"}})
    session = AsyncMock()
    session.get = lambda *a, **k: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 9999999999}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = await fetch_monthly_usage_from_oauth(lang_zh=False)

    assert row is None
    assert "totalQuota" in reason


@pytest.mark.asyncio
async def test_fetch_monthly_usage_from_oauth_reports_http_status(tmp_path, monkeypatch):
    ...  # 同上，但 cm.status = 401
    assert row is None
    assert "401" in reason


def test_load_token_state_reports_expired_token(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 1}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    token, reason = _load_token_state()  # noqa: F821  (从模块导入)
    assert token is None
    assert "expired" in reason


def test_load_token_state_reports_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH",
        str(tmp_path / "nope.json"),
    )
    token, reason = _load_token_state()
    assert token is None
    assert "no Kimi CLI credential file" in reason
```

- [ ] **Step 3: 追加 WebBridge 来源标记用例**

```python
@pytest.mark.asyncio
async def test_fetch_monthly_usage_marks_web_bridge_source():
    responses = [
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)):
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert row.label == "Monthly Credits (web)"
    assert row.used == 25.0


@pytest.mark.asyncio
async def test_fetch_monthly_usage_marks_web_bridge_source_zh():
    ...  # 同上，lang_zh=True
    assert row.label == "月度额度（网页）"
```

（注意：`test_parse_monthly_usage_snapshot_reads_first_total_card_in_usage_progress` 的 `row.label == "Monthly Credits"` **保持不变**——标记只加在 fetcher 层，解析器保持纯净。）

- [ ] **Step 4: 改造并追加 `_monthly_usage_row` 用例（`tests/test_provider_kimi.py`）**

```python
# 既有用例改为二元组
new=AsyncMock(return_value=(oauth_row, "")),
# ...
new=AsyncMock(return_value=(None, "response has no totalQuota")),
```

```python
@pytest.mark.asyncio
async def test_monthly_usage_row_reports_both_sources_when_unavailable():
    from kimi_code_usage.providers.kimi import _monthly_usage_row

    with patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_oauth",
        new=AsyncMock(return_value=(None, "access token expired at 2026-09-29 13:45")),
    ), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=MonthlyUsageUnavailable("Kimi WebBridge daemon is not running.")),
    ):
        row = await _monthly_usage_row()

    assert row.unit == "text"
    assert "expired" in row.text_value
    assert "daemon is not running" in row.text_value
```

- [ ] **Step 5: 跑测试确认失败**

Run: `uv run pytest tests/test_provider_kimi_membership.py tests/test_provider_kimi.py -q`
Expected: FAIL（`_load_token_state` 未定义；二元组解包 `TypeError`；标签无 `(web)`）

---

### Task 4: 实现 `kimi.py`（蛇形键 + `usages` 回退 + 月度失败消息）

**Files:**
- Modify: `src/kimi_code_usage/providers/kimi.py`

**Interfaces:**
- Consumes: Task 5 的 `fetch_monthly_usage_from_oauth(...) -> tuple[ProviderUsage | None, str]`（仅 Step 5 需要）
- Produces（新增模块级私有接口）：

  ```python
  def _window_minutes(window: Any) -> float | None
  def _ratio_usage_row(entry: Mapping[str, Any], label: str) -> KimiRow | None
  ```

- [ ] **Step 1: 新增 `_window_minutes`（放在 `_limit_label` 之后）**

窗口时长归一化为分钟：含 `MINUTE`→`duration`；`HOUR`→×60；`DAY`→×1440；`MONTH`→×43200；无单位→按秒（`/60`，与既有 `_limit_label` 的秒约定一致）。非 Mapping 或无 `duration` → `None`。

- [ ] **Step 2: 新增 `_ratio_usage_row`（放在 `_to_usage_row` 之后）**

`_ratio_usage_row` 规则：
- `entry["used_ratio"]` 非 `int | float` → 返回 `None`；
- `percent = max(0.0, min(float(ratio) * 100.0, 100.0))`（E2：0–1 比例）；
- 返回 `KimiRow(label=label, used=round(percent), limit=100, reset_at=..., countdown=...)`，重置信息复用 `_get_reset_info(entry)`（已支持 `reset_time`）。
- 说明：`KimiRow.used/limit` 是 `int`，故这里放弃 0.1631 的亚百分点精度（渲染本就取整），换得不改动 `KimiRow` 类型。

- [ ] **Step 3: 在 `_parse_usage_payload` 的 `else` 分支接入回退**

遍历 `limits` 时收集 `_window_minutes(window)` 到 `limit_windows`——**窗口覆盖以实际出行为准：仅登记确实产出了行的窗口**（若在确认 `detail` 能产出行之前就登记，一个不产行的 300 分钟条目会登记该窗口，进而静默吞掉本可用的 `limit_5h` 回退）——随后**注意 `limit_7d` 是周窗口，必须回填 `summary`（而非塞进 `limits`）**：

```python
                window_minutes = _window_minutes(window)
                row = _to_usage_row(detail, default_label=_limit_label(window, idx))
                if row:
                    limits.append(row)
                    if window_minutes is not None:
                        limit_windows.append(window_minutes)
```

```python
        usages = payload.get("usages")
        if isinstance(usages, Mapping):
            if summary is None:
                entry = usages.get("limit_7d")
                row = _ratio_usage_row(entry, "Weekly Usage") if isinstance(entry, Mapping) else None
                if row is not None:
                    summary = row
            if 300.0 not in limit_windows:
                entry = usages.get("limit_5h")
                row = _ratio_usage_row(entry, "5h Limit") if isinstance(entry, Mapping) else None
                if row is not None:
                    limits.append(row)
```

- [ ] **Step 4: `_extra_usage_rows` 读蛇形键**

```python
    wallet = payload.get("booster_wallet") or payload.get("boosterWallet")
```

其余（`totalQuota` / `parallel` / 单位 `"¥"` / 各分支）**逐字不动**。

- [ ] **Step 5: `_monthly_usage_row` 拼装两侧原因**

（**归属月度工作流**：本步依赖 Task 5 的二元组签名，实施顺序必须排在 Task 5 之后或与其同批，不得先于 Task 5。）

```python
async def _monthly_usage_row() -> ProviderUsage:
    try:
        oauth_row, oauth_reason = await fetch_monthly_usage_from_oauth(lang_zh=_KIMI_LANG_IS_ZH)
    except Exception as exc:
        oauth_row, oauth_reason = None, f"request failed: {exc}"
    if oauth_row is not None:
        return oauth_row
    try:
        return await fetch_monthly_usage_from_webbridge(lang_zh=_KIMI_LANG_IS_ZH)
    except Exception as exc:
        return ProviderUsage(
            provider="kimi",
            label="月度额度" if _KIMI_LANG_IS_ZH else "Monthly Credits",
            used=0.0,
            limit=None,
            remaining=None,
            percent=None,
            reset_at=None,
            unit="text",
            text_value=f"OAuth: {oauth_reason} | WebBridge: {exc}",
        )
```

- [ ] **Step 6: 跑测试**

Run: `uv run pytest tests/test_provider_kimi.py -q`
Expected: PASS

---

### Task 5: 实现 `kimi_membership.py`（失败原因 + 来源标记）

**Files:**
- Modify: `src/kimi_code_usage/providers/kimi_membership.py`

**Interfaces:**
- Produces: `_load_token_state() -> tuple[str | None, str]`、`fetch_monthly_usage_from_oauth(*, lang_zh: bool) -> tuple[ProviderUsage | None, str]`

- [ ] **Step 1: 抽出 `_load_token_state`，`load_kimi_cli_access_token` 变薄包装**

reason 取值集合（测试按子串断言，须逐字一致）：
- `"no Kimi CLI credential file"`（`OSError`）
- `"credential file is not readable JSON"`（`json.JSONDecodeError`）
- `"credential file has no access_token"`
- `f"access token expired at {datetime.fromtimestamp(expires_at):%Y-%m-%d %H:%M}"`
- 成功时 `""`

```python
def load_kimi_cli_access_token() -> str | None:
    return _load_token_state()[0]
```

（既有 3 个 `load_kimi_cli_access_token` 用例不改动，必须继续通过。）

- [ ] **Step 2: `fetch_monthly_usage_from_oauth` 返回二元组**

```python
async def fetch_monthly_usage_from_oauth(*, lang_zh: bool) -> tuple[ProviderUsage | None, str]:
```

reason 取值：
- 无 token → `_load_token_state()` 的 reason；
- `resp.status != 200` → `f"HTTP {resp.status}"`；
- `payload` 非 Mapping，或 `totalQuota` 非 Mapping，或 `used/limit` 解析失败或 `limit <= 0` → `"response has no totalQuota"`；
- 网络异常 → `f"request failed: {exc}"`；
- 成功 → `(row, "")`。

- [ ] **Step 3: WebBridge 结果打来源标记**

在 `fetch_monthly_usage_from_webbridge` 的快照循环中，取到 `row` 后：

```python
            if row is not None:
                row.label = "月度额度（网页）" if lang_zh else "Monthly Credits (web)"
                return row
```

（`parse_monthly_usage_snapshot` 保持纯净、标签仍为 `Monthly Credits`/`月度额度`。）

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_provider_kimi_membership.py tests/test_provider_kimi.py -q`
Expected: PASS

---

### Task 6: 全量质检 + 一文件一提交 + PR

- [ ] **Step 1: 质检**

```bash
uv run ruff check
uv run mypy 2>&1 | tail -5                 # 软失败，无新增错误即可
uv run pytest --cov=kimi_code_usage --cov-report=term-missing
uv run coverage report                     # fail_under=85
```

Expected: ruff clean；mypy 无新增错误；`pytest` 全绿（>312）；coverage ≥ 85%，且 `kimi.py` / `kimi_membership.py` 不低于基线。其中 `kimi.py` 必须回到基线 **96%**（本分支新增的 `_window_minutes` / `_ratio_usage_row` 分支需补分支测试达成，不能靠总覆盖率掩盖）。

- [ ] **Step 2: 变异校验（证明测试真的钉住了修复）**

对以下 4 处各注入一次反向变异，确认**至少一个测试失败**，然后还原：
1. `kimi.py`：`booster_wallet` → 改回只读 `boosterWallet`；
2. `kimi.py`：`used_ratio * 100.0` → 去掉 `* 100.0`；
3. `kimi.py`：`oauth_reason` → 从 `text_value` 中删掉；
4. `kimi_membership.py`：删掉 `row.label = ...` 来源标记。

- [ ] **Step 3: 一文件一提交（5 个 commit，中英双语）**

```bash
rtk git add docs/superpowers/plans/2026-10-19-kimi-usages-payload-shape.md
rtk git commit -m "docs(plan): plan the Kimi /usages payload-shape fixes

docs(plan): 制定 Kimi /usages 响应形状修复计划"

rtk git add tests/test_provider_kimi.py
rtk git commit -m "test(kimi): pin snake_case booster wallet and usages window shapes

test(kimi): 钉住蛇形 booster_wallet 与 usages 窗口形状"

rtk git add tests/test_provider_kimi_membership.py
rtk git commit -m "test(kimi): pin monthly source marker and oauth failure reasons

test(kimi): 钉住月度来源标记与 OAuth 失败原因"

rtk git add src/kimi_code_usage/providers/kimi_membership.py
rtk git commit -m "fix(kimi): report why the oauth monthly probe failed and mark web-sourced rows

fix(kimi): 暴露 OAuth 月度探测失败原因，并标记来源为网页的月度行"

rtk git add src/kimi_code_usage/providers/kimi.py
rtk git commit -m "fix(kimi): read the live /usages shape (snake_case booster_wallet, usages windows)

fix(kimi): 适配 live /usages 形状（蛇形 booster_wallet、usages 窗口）"
```

- [ ] **Step 4: 停止，征求 push/PR 同意**

推送前必须获得用户明确同意，然后：

```bash
rtk git push -u origin fix/kimi-usages-payload
rtk gh pr create --title "fix(kimi): adapt to the live /usages payload shape" --body-file <pr-body>
```

CI 通过后才谈合入；合入后按 AGENTS.md 收尾（`git pull --ff-only`、`worktree remove`、`branch -d`、删远端分支）。

---

## Self-Review

**1. Spec coverage:** 用户选定的 ①（真实缺陷 + 显式化回退）三项对应 Task 1（`booster_wallet`）、Task 2（`usages` 回退）、Task 3/4/5（显式化）。研究结论（月度结构性依赖网页侧）落地为 Task 3/5 的来源标记，而非删除 OAuth 路径（③ 未被选择）。无遗漏项。

**2. Step scan:** 每个测试步骤给出测试名与完整断言；每个实现步骤给出签名 + 被钉死的常量（`300.0`/`10080.0`/`×100`/clamp）与逐字 reason 文案。没有"处理边界情况"式的空步骤。

**3. Type consistency:** `fetch_monthly_usage_from_oauth` 由 `ProviderUsage | None` 变为 `tuple[ProviderUsage | None, str]`，三处调用点（`kimi.py:236`、2 个测试）全部在 Task 3/4 内同步更新；`_load_token_state` 命名在 Task 3（测试）与 Task 5（实现）一致；`_window_minutes`/`_ratio_usage_row` 在 Task 2（测试间接）与 Task 4（实现）一致。

---

## 执行分组（SDD 控制器使用）

三个批次，每批结束时代码全绿（避免出现"测试先行但必红"的批次）：

- **批次 D1 = Task 1 + Task 2 + Task 4 Step 1–4**（coding API 侧解析：`kimi.py` + `tests/test_provider_kimi.py`）
- **批次 D2 = Task 3 + Task 4 Step 5 + Task 5**（月度来源：`kimi_membership.py` + `kimi.py::_monthly_usage_row` + 两个测试文件）
- **批次 D3 = Task 6**（质检 + 变异校验 + 按文件重建提交；**禁止 push**）

提交粒度裁决：各批次实现者可自由提交以便评审取 diff；批次 D3 结束时按"一文件一提交"重建分支历史（未 push，无共享状态风险）。

**4. Review Focus:** 5 条各有点测：① → `test_parse_usage_payload_ignores_usages_when_usage_and_limits_present`；② → `..._clamps_out_of_range_ratio` + `..._falls_back_to_usages_windows`（0.1631→16）；③ → 同上断言 `limit == 100`；④ → `test_monthly_usage_row_reports_both_sources_when_unavailable`；⑤ → Task 1 既有 camelCase 用例 + `test_extra_usage_rows_snake_case_wins_over_camel_case` + 全量 312 条基线。

**5. Proportion:** 计划短于其覆盖的实现改动，未逐行转写函数体。

**已知取舍（需用户知悉）:**
- `usages` 回退在**今天不会触发**（`usage`/`limits` 已覆盖两个窗口）——它是针对已实测存在的形状漂移（`totalQuota` 消失）的防护，而非当前缺陷修复。
- `totalQuota` / `parallel` 分支保持原样（未验证语义，按"外科手术"原则不删）；社区文档称 `totalQuota` 实为"月度冻结标志"，若将来复现需单独决策。
- `Monthly Credits (web)` 标记是**当前恒定状态**的诚实呈现；若将来 OAuth 路径真能取到月度，标记会自动消失。
