# VS Code Extension TypeScript 严格度升级设计文档

## 目标

将 `vscode-extension` 项目从"已 TypeScript 化"推进到"类型严格安全"，消除编译期盲区，为后续功能扩展（如 WebView 类型化通信）奠定类型基础。

## 现状分析

| 指标 | 当前状态 |
|---|---|
| `.ts` 源码覆盖率 | ~96%（23/24 个文件） |
| `strict` 模式 | 已启用 |
| `any` 使用 | 零使用 |
| `@ts-ignore` | 零使用 |
| 遗留 JS 文件 | `vitest.config.js` + `.map`、`scripts/copy-assets.mjs` |
| 内联 JS | `webview-chart-test.html` 内含 ~360 行 JS（本次不涉及） |

## 设计原则

1. **零行为变更** — 本次重构只改动类型层面，不修改运行时逻辑
2. **配置驱动** — 通过 `tsconfig.json` 严格选项暴露潜在问题，再逐一修复
3. **可回滚** — 每个改动独立提交，出问题可单独 revert

## 具体改动项

### 1. 清理遗留文件

删除以下文件（它们已有 TS 版本或不再需要）：

- `vitest.config.js`
- `vitest.config.js.map`

### 2. 升级 `tsconfig.json` 严格选项

在现有 `strict: true` 基础上新增：

```json
{
  "compilerOptions": {
    "exactOptionalPropertyTypes": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true
  }
}
```

各选项作用：

| 选项 | 作用 | 预期影响 |
|---|---|---|
| `exactOptionalPropertyTypes` | 区分 `prop?: string` 与 `prop: string \| undefined` | 需检查对象字面量赋值 |
| `noUncheckedIndexedAccess` | `arr[i]`、`obj[k]` 返回类型附加 `\| undefined` | 需补充空值检查 |
| `noImplicitReturns` | 所有代码路径必须显式返回 | 需检查条件分支 |
| `noFallthroughCasesInSwitch` | switch 的 case 不允许隐式贯穿 | 需检查 switch 语句 |

### 3. 迁移构建脚本到 TypeScript

将 `scripts/copy-assets.mjs` 改写为 `scripts/copy-assets.ts`：

- 添加类型注解（`fs/promises` 返回类型、`path` 参数类型）
- 添加 JSDoc 注释说明脚本用途
- 更新 `package.json` scripts：
  - `"assets": "tsx scripts/copy-assets.ts"`（使用 `tsx` 直接运行 TS）
- `devDependencies` 新增 `tsx`

### 4. 修复暴露出的类型问题

运行 `tsc --noEmit` 后，根据错误列表逐一修复：

- **索引访问**：`array[i]` → `array[i]!`（确认安全后）或添加空值处理
- **可选属性**：检查对象构造时是否误传了 `undefined`
- **隐式返回**：为条件分支补充 `return` 或抛出异常
- **switch 贯穿**：为 case 添加 `break` 或 `// fallthrough` 注释

### 5. ESLint 配置同步收紧

`eslint.config.mjs` 中开启以下规则（与 TS 严格选项对齐）：

```js
'@typescript-eslint/no-unnecessary-condition': 'error',
'@typescript-eslint/strict-boolean-expressions': 'warn',
```

## 验证步骤

1. `tsc --noEmit` 零错误
2. `npm run test` 全部通过
3. `npm run build` 成功生成
4. `npm run lint` 无警告（或仅容忍已知警告）
5. 手动验证扩展在 VS Code 中正常激活

## 风险与回滚策略

| 风险 | 缓解措施 |
|---|---|
| 严格选项引入过多错误 | 分阶段启用，每次只加一项，修复后再加下一项 |
| 运行时行为意外变更 | 保持逻辑不变，仅添加类型断言或空值检查 |
| 构建脚本迁移后失败 | 保留 `copy-assets.mjs` 直至 `copy-assets.ts` 验证通过 |

## 后续升级路径（方案 C 预留）

本次完成后，后续可考虑：

1. 将 `webview-chart-test.html` 内联 JS 抽取为 `webview/chart.ts`
2. 为 webview ↔ extension 通信引入 `WebviewMessage<T>` 泛型协议
3. 为 `historyPanel.ts` 的 HTML 模板引入类型安全生成器

## 范围边界

**本次不做：**
- 不迁移 `webview-chart-test.html` 的内联 JS
- 不引入新的构建工具（如 esbuild、rollup）
- 不修改任何运行时逻辑或 UI 行为
- 不改动 Python 后端代码
