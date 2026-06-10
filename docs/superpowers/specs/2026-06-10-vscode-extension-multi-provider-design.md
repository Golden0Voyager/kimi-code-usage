# VS Code Extension Multi-Provider Integration Design

> 将多 LLM provider（OpenAI、Anthropic、OpenRouter）用量查询集成到 kimi-code-usage VS Code 扩展中，与现有 Python CLI/MCP 端设计保持一致。

## 1. 目标

将当前仅支持 Kimi 的 VS Code 扩展升级为支持多 provider 用量查询，同时保持：

- **向后兼容** — 现有 Kimi 配置 (`kimiCodeUsage.apiKey`、`kimiCodeUsage.baseUrl`) 继续有效
- **零侵入** — 不修改历史面板 (WebView chart)、不修改缓存机制
- **配置优先** — 通过 VS Code 设置面板完成所有 provider 管理
- **简单可靠** — 状态栏单显示 + tooltip 汇总 + 两级 QuickPick 详情

## 2. 整体架构

```
extension.ts (激活)
    │
    ├─ config.ts 扩展
    │    ┌─────────────────────────────┐
    │    │ ProviderConfigResolver      │ ← 读取所有 provider 配置
    │    │  - kimiConfig (现有保留)     │
    │    │  - providers.{id} 分组      │
    │    │  - displayProvider 选择     │
    │    └─────────────────────────────┘
    │
    ├─ api.ts 扩展
    │    ┌─────────────────────────────┐
    │    │ ProviderFetchers            │ ← 各 provider HTTP 请求
    │    │  - fetchUsage()        (Kimi, 不变)
    │    │  - fetchOpenAIUsage()  (新增)
    │    │  - fetchAnthropicUsage()(新增)
    │    │  - fetchOpenRouterUsage()(新增)
    │    └────────────┬────────────────┘
    │                 │
    │    ┌────────────▼────────────────┐
    │    │ fetchAllProviders()         │ ← 并行调度所有 enabled provider
    │    └────────────┬────────────────┘
    │                 │
    │    ┌────────────▼────────────────┐
    │    │ ProviderUsageAggregator     │ ← 聚合+错误包装
    │    └────────────┬────────────────┘
    │                 │
    ├─ statusBar.ts 重构
    │    ┌────────────▼────────────────┐
    │    │ SingleDisplayStrategy       │ ← 按 displayProvider 选择展示
    │    │  - text: 所选 provider 概要  │
    │    │  - tooltip: 全部 provider   │
    │    └─────────────────────────────┘
    │
    ├─ quickPick.ts (新增)
    │    ┌─────────────────────────────┐
    │    │ ProviderQuickPick           │ ← 两级选择器
    │    │  1st: 选 provider           │
    │    │  2nd: 选窗口 (现有逻辑)      │
    │    └─────────────────────────────┘
    │
    └─ notifier.ts 扩展
         ┌─────────────────────────────┐
         │ NotificationManager         │ ← 多 provider 独立阈值检查
         └─────────────────────────────┘
```

**数据流：**

1. `extension.activate()` → 读取配置 → 注册命令 → 首次刷新
2. `refresh()` → `refreshOnce()` → `fetchAllProviders()` → 并行 HTTP 请求
3. `fetchAllProviders()` 返回 `ProviderUsageResult[]`
4. `statusBar` 按 `displayProvider` 渲染主显示 → tooltip 渲染全部
5. 用户点击状态栏 → `showDetails()` → `ProviderQuickPick` 两级选择

## 3. 配置项设计

### 3.1 新增设置项

在 `package.json` 的 `contributes.configuration.properties` 中新增：

```json
{
  "kimiCodeUsage.displayProvider": {
    "type": "string",
    "default": "kimi",
    "enum": ["kimi", "openai", "anthropic", "openrouter"],
    "enumDescriptions": [
      "Kimi (Coding Plan)",
      "OpenAI API",
      "Anthropic API / Claude",
      "OpenRouter API"
    ],
    "description": "Select which provider to show on the status bar / 状态栏显示的 provider",
    "order": 3
  },

  "kimiCodeUsage.providers": {
    "type": "object",
    "default": {},
    "description": "Multi-provider API configurations / 多 Provider API 配置",
    "order": 21,
    "properties": {
      "openai": {
        "type": "object",
        "default": {},
        "properties": {
          "apiKey": { "type": "string", "default": "" },
          "enabled": { "type": "boolean", "default": false }
        }
      },
      "anthropic": {
        "type": "object",
        "default": {},
        "properties": {
          "apiKey": { "type": "string", "default": "" },
          "enabled": { "type": "boolean", "default": false }
        }
      },
      "openrouter": {
        "type": "object",
        "default": {},
        "properties": {
          "apiKey": { "type": "string", "default": "" },
          "enabled": { "type": "boolean", "default": false }
        }
      }
    }
  }
}
```

### 3.2 配置优先级（与 CLI 一致）

| 来源 | 优先级 | 说明 |
|---|---|---|
| VS Code 设置 `kimiCodeUsage.providers.{id}.apiKey` | 最高 | JSON UI 配置 |
| 环境变量 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | 中 | 回退读取 |
| 预留 `~/.kimi-usage/config.json` | 低 | 未来可扩展 |

### 3.3 现有 Kimi 配置向后兼容

- `kimiCodeUsage.apiKey` / `kimiCodeUsage.baseUrl` 继续有效
- 如果设置了 `kimiCodeUsage.providers.kimi.apiKey`，则优先使用
- `resolveApiKey()` 改造为 `resolveProviderConfig(providerId)` 通用函数

## 4. 类型扩展

在 `src/types.ts` 中新增：

```typescript
export type ProviderId = 'kimi' | 'openai' | 'anthropic' | 'openrouter';

export interface ProviderConfig {
  apiKey: string;
  baseUrl?: string;    // Kimi 特有
  enabled: boolean;
}

export interface ProviderUsageResult {
  provider: ProviderId;
  label: string;       // 显示名称，如 "Kimi", "OpenAI"
  items: UsageItem[];
  error?: string;      // 如果该 provider 请求失败
}

export interface MultiProviderState {
  results: ProviderUsageResult[];
  fetchedAt: number;
  errors: { provider: ProviderId; message: string }[];
}
```

## 5. 核心模块实现

### 5.1 Provider Fetchers (`src/api.ts` 扩展)

新增三个 fetch 函数 + 并行调度函数：

```typescript
// === OpenAI ===
function fetchOpenAIUsage(apiKey: string): Promise<UsageItem[]> {
  // GET https://api.openai.com/v1/organization/usage/completions
  // → token counts → 转为 UsageItem
  // label: "Completions"
  // 如果 org admin key 不可用，返回 []
}

// === Anthropic ===
function fetchAnthropicUsage(apiKey: string): Promise<UsageItem[]> {
  // GET https://api.anthropic.com/api/oauth/usage
  // → five_hour.utilization, seven_day.utilization → 转为 UsageItem[]
  // label: "7 Day", "5 Hour"
  // API key 用户返回 "API plan - no usage endpoint"
}

// === OpenRouter ===
function fetchOpenRouterUsage(apiKey: string): Promise<UsageItem[]> {
  // GET https://openrouter.ai/api/v1/auth/key
  // → data.usage, data.limit (USD) → 转为 UsageItem[]
  // label: "Credits"
}

// === 并行调度 ===
async function fetchAllProviders(
  configs: Record<ProviderId, ProviderConfig>
): Promise<ProviderUsageResult[]> {
  const tasks: Promise<ProviderUsageResult>[] = [];
  for (const [id, cfg] of Object.entries(configs)) {
    if (!cfg.enabled || !cfg.apiKey) continue;
    tasks.push(fetchSingleProvider(id as ProviderId, cfg));
  }
  const results = await Promise.allSettled(tasks);
  // 聚合成功/失败结果
}
```

### 5.2 StatusBar 重构 (`src/statusBar.ts`)

**`refreshOnce()` 修改为：**

```typescript
async function refreshOnce(): Promise<void> {
  // 1. 读取所有 provider 配置
  const configs = readAllProviderConfigs();

  // 2. 并行 fetch
  const results = await fetchAllProviders(configs);

  // 3. 保存聚合状态（供 QuickPick 使用）
  currentMultiProviderState = {
    results,
    fetchedAt: Date.now(),
    errors: extractErrors(results),
  };

  // 4. 按 displayProvider 渲染 statusBar
  const displayProvider = cfg.get<string>('displayProvider', 'kimi');
  const selected = results.find(r => r.provider === displayProvider);
  if (selected && selected.items.length > 0) {
    renderStatusBar(selected);
  } else {
    renderFallback(results);
  }

  // 5. tooltip 渲染所有 provider 摘要
  renderTooltip(results, errors);
}
```

**tooltip 格式示例：**

```
**Usage Telemetry**
- Kimi: Weekly 96% | 5H 99%
- OpenAI: $45.20 / $100.00
- Anthropic: 7d 45%, 5h 12%

**Errors**
- ⚠ Anthropic: API unreachable
```

### 5.3 详情面板 (`src/quickPick.ts` 新增)

将 `statusBar.ts` 中的 `showDetails()` 逻辑抽取为独立的 `ProviderQuickPick` 类：

```typescript
class ProviderQuickPick {
  async show(): Promise<void> {
    // 1. 第一级：选择 provider
    const provider = await pickProvider(results);
    if (!provider) return;

    // 2. 第二级：显示该 provider 的窗口详情（现有逻辑）
    await showWindowDetails(provider);
  }
}
```

第一级 UI 示例：

```
☀ Kimi        Weekly: 96%  5H: 99%
○ OpenAI      $45.20 / $100.00
● Anthropic   7d: 45%  5h: 12%
⚠ OpenRouter  Not configured
```

选中某个 provider 后进入第二级（调用现有 `showDetails()` 中的窗口详情逻辑）。

### 5.4 Notification 扩展 (`src/notifier.ts`)

`checkAndNotify()` 改为遍历所有结果：

```typescript
class Notifier {
  async checkAndNotify(results: ProviderUsageResult[]): Promise<void> {
    for (const result of results) {
      for (const item of result.items) {
        const type = detectWindowType(item.label);
        const thresholds = this.getThresholds(result.provider, type);
        if (item.percent_left < thresholds.warning) {
          this.showNotification(result.provider, item, thresholds);
        }
      }
    }
  }
}
```

## 6. API 详细端点

### Kimi（不变）

| 项 | 值 |
|---|---|
| 端點 | `GET {baseUrl}/usages` |
| 认证 | `Authorization: Bearer {apiKey}` |
| 返回 | `UsageItem[]` (weekly/5h/monthly) |

### OpenAI

| 项 | 值 |
|---|---|
| 端点 | `GET https://api.openai.com/v1/organization/usage/completions` |
| 参数 | `start_time`, `end_time`, `bucket_width=1d`, `limit=7` |
| 认证 | `Authorization: Bearer {apiKey}`（需要 org admin key） |
| 返回 | Token 用量（input/output/cached）→ `UsageItem[]` |
| 备选 | `GET /v1/organization/usage/costs` 获取费用 |

### Anthropic

| 项 | 值 |
|---|---|
| 端点 | `GET https://api.anthropic.com/api/oauth/usage` |
| 认证 | `Authorization: Bearer {apiKey}`（OAuth token） |
| 返回 | `five_hour.utilization`, `seven_day.utilization` (0-100%) |
| 回退 | API key 用户无用量端点，显示提示信息 |

### OpenRouter

| 项 | 值 |
|---|---|
| 端点 | `GET https://openrouter.ai/api/v1/auth/key` |
| 认证 | `Authorization: Bearer {apiKey}` |
| 返回 | `data.usage`, `data.limit` (USD) → `UsageItem` |

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| Provider 未启用或 key 为空 | 跳过，不显示 Error |
| provider API 不可达 | `result.error = "API unreachable"`，tooltip 显示 |
| 鉴权失败 (401/403) | `result.error = "Invalid key"`，tooltip 显示 |
| 限流 (429) | `result.error = "Rate limited, retry after Xs"` |
| 超时 | `result.error = "Request timed out"` |
| 所选 displayProvider 不可用 | StatusBar 回退显示第一个可用 provider 或错误状态 |

## 8. 文件改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/types.ts` | 修改 | 新增 `ProviderId`, `ProviderConfig`, `ProviderUsageResult`, `MultiProviderState` 类型 |
| `src/api.ts` | 修改 | 新增 `fetchOpenAIUsage()`, `fetchAnthropicUsage()`, `fetchOpenRouterUsage()`, `fetchAllProviders()` |
| `src/config.ts` | 修改 | 新增 `resolveProviderConfig()`, `readAllProviderConfigs()`, 保留向后兼容 |
| `src/statusBar.ts` | 修改 | `refreshOnce()` 改为多 provider 并行调度 + 单显示策略 |
| `src/quickPick.ts` | **新建** | `ProviderQuickPick` 两级选择器（抽取自 `showDetails()`） |
| `src/extension.ts` | 修改 | 注册新命令 `kimiCodeUsage.showDetailForProvider`（可选） |
| `src/notifier.ts` | 修改 | 多 provider 告警 |
| `package.json` | 修改 | 新增 `displayProvider`, `providers` 设置项 |

## 9. CLI API 对应关系

| CLI 功能 | VS Code 对等物 |
|---|---|
| `kimi-usage --provider kimi` | `kimiCodeUsage.displayProvider = "kimi"` |
| `kimi-usage --json` | N/A（VS Code 扩展无 JSON 输出） |
| `kimi-usage --config` | VS Code settings.json 原生支持 |
| `kimi-usage --provider kimi,openai` | 自动拉取所有 enabled provider |
| `~/.kimi-usage/config.json` | VS Code 设置 + 环境变量（优先级一致） |

## 10. 非目标

- 不修改 WebView chart / `historyPanel.ts` — 历史快照仍以 Kimi 为主
- 不修改 `apiCache.ts` 缓存结构 — 仅用 providerId 扩展 key
- 不引入 OAuth 流程 — Anthropic OAuth token 和 API key 一样通过配置项设置
- 不做 WebView 中的多 provider 图表展示
- 不修改 test 结构

## 11. 向后兼容说明

| 现有行为 | 升级后行为 |
|---|---|
| `kimiCodeUsage.apiKey` 设但未设 `providers` | Kimi 自动可用（`config.ts` fallback 逻辑） |
| `kimiCodeUsage.baseUrl` 已设 | 继续用于 Kimi fetch |
| `refreshOnce()` 只拉取 Kimi | 改为拉取所有 enabled provider |
| `showDetails()` QuickPick | 新增一级 provider 选择，窗口详情逻辑不变 |
| 通知阈值设置 | 继续有效，仅对 Kimi provider 生效 |
