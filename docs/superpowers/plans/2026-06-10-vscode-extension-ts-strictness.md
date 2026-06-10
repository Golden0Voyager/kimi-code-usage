# VS Code Extension TypeScript 严格度升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `vscode-extension` 项目的 TypeScript 配置升级至最严格级别，消除编译期盲区，同时迁移构建脚本至 TypeScript。

**Architecture:** 通过逐步启用 4 项 `tsconfig.json` 严格编译选项，暴露潜在类型问题并逐一修复；使用 `tsx` 直接运行 TypeScript 构建脚本，替代原有的 `.mjs` 方案。

**Tech Stack:** TypeScript 5.x, `tsx`, VS Code Extension API, ESLint, Vitest

---

## 文件结构映射

| 文件 | 操作 | 说明 |
|---|---|---|
| `vitest.config.js` | 删除 | 遗留编译产物，已有 `.ts` 版本 |
| `vitest.config.js.map` | 删除 | 遗留 source map |
| `scripts/copy-assets.mjs` | 删除（Task 3 后） | 原 JS 构建脚本 |
| `scripts/copy-assets.ts` | 创建 | TypeScript 版本的构建脚本 |
| `tsconfig.json` | 修改 | 添加 4 项严格选项 |
| `package.json` | 修改 | 添加 `tsx` 依赖，更新 `assets` script |
| `eslint.config.mjs` | 修改 | 添加 2 条类型安全规则 |
| `src/**/*.ts` | 修改 | 修复严格选项暴露的类型问题 |

---

## Task 1: 清理遗留编译产物

**Files:**
- 删除: `vitest.config.js`
- 删除: `vitest.config.js.map`

- [ ] **Step 1: 确认遗留文件存在**

```bash
cd /Users/hainingyu/Code/kimi_usage/vscode-extension
ls -la vitest.config.js vitest.config.js.map
```

Expected: 两个文件都存在

- [ ] **Step 2: 删除遗留文件**

```bash
git rm vitest.config.js vitest.config.js.map
```

- [ ] **Step 3: 验证删除后 `vitest.config.ts` 仍在**

```bash
ls -la vitest.config.ts
```

Expected: `vitest.config.ts` 存在

- [ ] **Step 4: 验证测试仍可运行**

```bash
npx vitest run --run
```

Expected: 所有测试通过

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy vitest.config.js artifacts

删除遗留的 vitest.config.js 及其 source map。"
```

---

## Task 2: 安装 tsx 并迁移构建脚本

**Files:**
- 创建: `scripts/copy-assets.ts`
- 修改: `package.json`
- 删除: `scripts/copy-assets.mjs` (Step 6)

- [ ] **Step 1: 安装 tsx**

```bash
cd /Users/hainingyu/Code/kimi_usage/vscode-extension
npm install -D tsx
```

Expected: `package.json` 和 `package-lock.json` 更新

- [ ] **Step 2: 创建 `scripts/copy-assets.ts`**

```typescript
import { copyFile, mkdir, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const src = path.join(root, 'node_modules', 'chart.js', 'dist', 'chart.umd.js');
const destDir = path.join(root, 'out', 'media');
const dest = path.join(destDir, 'chart.umd.js');

async function main(): Promise<void> {
  try {
    await access(src);
  } catch {
    console.error(`[copy-assets] missing ${src}. Did you run "npm install"?`);
    process.exit(1);
  }

  await mkdir(destDir, { recursive: true });
  await copyFile(src, dest);
  console.log(`[copy-assets] ${path.relative(root, src)} -> ${path.relative(root, dest)}`);
}

main();
```

- [ ] **Step 3: 更新 `package.json` 中的 `assets` script**

在 `package.json` 中找到 `"assets": "node scripts/copy-assets.mjs"`，改为：

```json
"assets": "tsx scripts/copy-assets.ts"
```

- [ ] **Step 4: 验证新脚本可运行**

```bash
npm run assets
```

Expected: 输出类似 `[copy-assets] node_modules/chart.js/dist/chart.umd.js -> out/media/chart.umd.js`

- [ ] **Step 5: 验证完整构建链**

```bash
npm run build
```

Expected: `tsc` 编译成功，`assets` 复制成功

- [ ] **Step 6: 删除旧的 `.mjs` 脚本**

```bash
git rm scripts/copy-assets.mjs
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: migrate copy-assets script to TypeScript

使用 tsx 直接运行 TypeScript 构建脚本，替代 .mjs。"
```

---

## Task 3: 启用 `noImplicitReturns` 与 `noFallthroughCasesInSwitch`

**Files:**
- 修改: `tsconfig.json`

这两项严格选项预计影响最小，先启用以建立信心。

- [ ] **Step 1: 在 `tsconfig.json` 中添加两项严格选项**

找到 `"forceConsistentCasingInFileNames": true` 这一行，在其后添加：

```json
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
```

- [ ] **Step 2: 运行类型检查**

```bash
npx tsc --noEmit
```

Expected: 零错误（当前代码已良好，这两项预计不会报错）

- [ ] **Step 3: 如有错误则修复**

如果 Step 2 报错，修复模式：

**`noImplicitReturns` 修复示例：**
```ts
// 修改前（某些路径无返回）
function foo(x: boolean): string {
  if (x) return "yes";
  // 隐式返回 undefined
}

// 修改后
function foo(x: boolean): string {
  if (x) return "yes";
  return "no"; // 或 throw new Error()
}
```

**`noFallthroughCasesInSwitch` 修复示例：**
```ts
// 修改前
switch (val) {
  case 'a':
    doA();
    // 漏了 break，fallthrough 到 case 'b'
  case 'b':
    doB();
    break;
}

// 修改后
switch (val) {
  case 'a':
    doA();
    break;
  case 'b':
    doB();
    break;
}
```

- [ ] **Step 4: 再次验证类型检查通过**

```bash
npx tsc --noEmit
```

Expected: 零错误

- [ ] **Step 5: Commit**

```bash
git add tsconfig.json
git commit -m "chore: enable noImplicitReturns and noFallthroughCasesInSwitch

启用两项 TypeScript 严格编译选项。"
```

---

## Task 4: 启用 `exactOptionalPropertyTypes`

**Files:**
- 修改: `tsconfig.json`
- 可能修改: `src/**/*.ts`（如有错误）

- [ ] **Step 1: 在 `tsconfig.json` 中添加选项**

在已有严格选项后面添加：

```json
    "exactOptionalPropertyTypes": true,
```

- [ ] **Step 2: 运行类型检查**

```bash
npx tsc --noEmit
```

记录所有错误的位置和消息。

- [ ] **Step 3: 修复 `exactOptionalPropertyTypes` 错误**

常见修复模式：

```ts
// 问题：将 undefined 赋给可选属性
interface Options {
  limit?: number;
}
const opts: Options = { limit: undefined }; // 错误！

// 修复方式 1：不设置该属性
const opts: Options = {};

// 修复方式 2：如果确实需要 undefined，修改接口
interface Options {
  limit?: number | undefined;
}
```

重点关注 `src/storage.ts` 中的 `ListOptions` 接口（`sinceMs?: number`, `limit?: number`），检查是否有传 `undefined` 的情况。

- [ ] **Step 4: 验证类型检查通过**

```bash
npx tsc --noEmit
```

Expected: 零错误

- [ ] **Step 5: Commit**

```bash
git add tsconfig.json src/
git commit -m "chore: enable exactOptionalPropertyTypes

启用精确可选属性类型，修复相关赋值问题。"
```

---

## Task 5: 启用 `noUncheckedIndexedAccess`（核心任务）

**Files:**
- 修改: `tsconfig.json`
- 修改: `src/api.ts`
- 修改: `src/historyPanel.ts`
- 可能修改: 其他源文件

这是影响最大的严格选项。数组/对象索引访问会返回 `| undefined`。

- [ ] **Step 1: 在 `tsconfig.json` 中添加选项**

```json
    "noUncheckedIndexedAccess": true,
```

- [ ] **Step 2: 运行类型检查，记录所有错误**

```bash
npx tsc --noEmit 2>&1 | tee /tmp/tsc-errors.txt
```

保存错误列表供后续修复。

- [ ] **Step 3: 修复 `src/api.ts` 中的索引访问**

预期修复点：`parsePayload` 函数中的 `limits[i]`（约第 76 行）：

```ts
// 修改前
for (let i = 0; i < limits.length; i++) {
  const item = limits[i];
  if (!item || typeof item !== 'object') continue;
  // ...
}

// 修改后（noUncheckedIndexedAccess 下 limits[i] 类型为 unknown | undefined）
for (let i = 0; i < limits.length; i++) {
  const item = limits[i];
  if (item === undefined) continue;
  if (typeof item !== 'object' || item === null) continue;
  // ...
}
```

以及 `limitLabel` 中的 `item[key]` 访问（约第 161 行）：

```ts
// 修改前
const value = item[key] ?? detail[key];

// 修改后
const value = (item as Record<string, unknown>)[String(key)] ?? (detail as Record<string, unknown>)[String(key)];
// 需要处理 undefined 情况
```

- [ ] **Step 4: 修复 `src/historyPanel.ts` 中的索引访问**

预期修复点：

**a) `buildSeries` 中的 `first.label`（约第 614-617 行）：**

```ts
// 修改前
const first = points[0];
return {
  // ...
  label: localizedLimitName(first.label) || first.label,
  // ...
};

// 修改后
const first = points[0];
if (first === undefined) return null; // 实际上 points.length > 0 已保证，但类型系统不知道
// 或：
const first = points[0]!; // 如果确定非空，使用非空断言
```

**b) `render` 函数中的 `s.points[s.points.length - 1]`（约第 320 行）：**

```ts
// 修改前
const latest = s.points[s.points.length - 1];

// 修改后
const latest = s.points[s.points.length - 1];
if (latest === undefined) return ''; // 或在合适的位置处理
```

**c) Chart.js 数据处理中的索引访问（约第 407-409 行）：**

```ts
// 修改前
const latest = data[data.length - 1];
const first = data[0];

// 修改后
const latest = data[data.length - 1];
const first = data[0];
// 后续代码中检查 undefined，或使用非空断言（如果逻辑上已保证）
```

**d) Tooltip callbacks 中的 `items[0]`（约第 534 行）：**

```ts
// 修改前
title: items => items.length ? fmtDate(items[0].parsed.x) : '',

// 修改后
title: items => items[0] !== undefined ? fmtDate(items[0].parsed.x) : '',
```

- [ ] **Step 5: 修复其他文件中的索引访问**

逐一处理 Step 2 记录的错误列表中剩余的问题。常见修复模式：

```ts
// 模式 1：非空断言（确定不会越界时）
const item = array[i]!;

// 模式 2：显式 undefined 检查
const item = array[i];
if (item === undefined) continue; // 或 return / throw

// 模式 3：类型守卫
function isDefined<T>(x: T | undefined): x is T {
  return x !== undefined;
}
const validItems = array.map(...).filter(isDefined);
```

- [ ] **Step 6: 验证类型检查通过**

```bash
npx tsc --noEmit
```

Expected: 零错误

- [ ] **Step 7: 运行测试确保无运行时回归**

```bash
npx vitest run
```

Expected: 所有测试通过

- [ ] **Step 8: Commit**

```bash
git add tsconfig.json src/
git commit -m "chore: enable noUncheckedIndexedAccess

启用未检查索引访问严格选项，为所有数组/对象索引访问添加 undefined 处理。"
```

---

## Task 6: 更新 ESLint 配置

**Files:**
- 修改: `eslint.config.mjs`

- [ ] **Step 1: 在 `eslint.config.mjs` 中添加两条规则**

在 `rules` 对象中添加：

```js
      '@typescript-eslint/no-unnecessary-condition': 'error',
      '@typescript-eslint/strict-boolean-expressions': 'warn',
```

完整的 rules 部分应如下所示：

```js
    rules: {
      ...tseslint.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'off',
      'no-empty': ['error', { allowEmptyCatch: true }],
      '@typescript-eslint/no-unnecessary-condition': 'error',
      '@typescript-eslint/strict-boolean-expressions': 'warn',
    },
```

- [ ] **Step 2: 运行 ESLint 检查**

```bash
npx eslint src
```

记录所有报告的问题。

- [ ] **Step 3: 修复 ESLint 问题**

**`no-unnecessary-condition` (`error`) 修复示例：**

```ts
// 问题：多余的类型检查
function process(items: string[]) {
  if (!items) return; // 错误：items 已经是 string[]，不会是 falsy
  // ...
}

// 修复：删除多余检查
function process(items: string[]) {
  // ...
}
```

```ts
// 问题：多余的 typeof 检查
if (typeof x === 'string' && x !== undefined) { // x !== undefined 多余
  // ...
}

// 修复：删除多余条件
if (typeof x === 'string') {
  // ...
}
```

**`strict-boolean-expressions` (`warn`) 修复示例：**

```ts
// 问题：模糊的布尔表达式
if (str) { // 警告：str 可能是空字符串
  // ...
}

// 修复：明确意图
if (str !== '') {
  // ...
}
```

```ts
// 问题：数字作为布尔值
if (count) { // 警告：count 为 0 时也是 falsy
  // ...
}

// 修复：明确比较
if (count > 0) {
  // ...
}
```

- [ ] **Step 4: 验证 ESLint 通过**

```bash
npx eslint src
```

Expected: 零 error（warn 可容忍）

- [ ] **Step 5: Commit**

```bash
git add eslint.config.mjs src/
git commit -m "chore: tighten ESLint rules for type safety

添加 no-unnecessary-condition (error) 和 strict-boolean-expressions (warn)。"
```

---

## Task 7: 最终验证

- [ ] **Step 1: 完整类型检查**

```bash
npx tsc --noEmit
```

Expected: 零错误

- [ ] **Step 2: 完整构建**

```bash
npm run build
```

Expected: 编译成功，`out/` 目录生成，assets 复制成功

- [ ] **Step 3: 运行所有测试**

```bash
npx vitest run
```

Expected: 所有测试通过

- [ ] **Step 4: 运行 ESLint**

```bash
npx eslint src
```

Expected: 零 error

- [ ] **Step 5: 运行 Prettier 格式检查**

```bash
npx prettier --check src
```

Expected: 无格式问题（如有则运行 `npm run format` 修复）

- [ ] **Step 6: 验证扩展可激活（如环境允许）**

按 F5 在 VS Code 中启动扩展宿主，确认扩展正常激活，状态栏显示正常。

- [ ] **Step 7: Commit（如需要）**

如果有格式修复的改动：

```bash
git add -A
git commit -m "style: apply prettier formatting

统一代码格式。"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec 要求 | 对应 Task |
|---|---|
| 删除 `vitest.config.js` + `.map` | Task 1 |
| 升级 `tsconfig.json` 严格选项 | Task 3, 4, 5 |
| 迁移 `copy-assets.mjs` → `.ts` | Task 2 |
| 更新 `package.json` scripts | Task 2 |
| 修复类型问题 | Task 4, 5, 6 |
| 更新 ESLint 配置 | Task 6 |
| 验证构建和测试 | Task 7 |

### Placeholder Scan

- [x] 无 "TBD"/"TODO"/"implement later"
- [x] 无 "Add appropriate error handling" 等模糊描述
- [x] 每个代码步骤都有完整代码示例
- [x] 每个命令都有预期输出

### Type Consistency

- [x] `ListOptions` 接口在 `src/storage.ts` 中定义，Task 4 修复时引用一致
- [x] `Snapshot` / `WindowType` 类型在 `src/types.ts` 中定义，各 Task 引用一致
- [x] ESLint 规则名称与 `eslint.config.mjs` 中使用的插件一致

---

## Rollback Guide

如果任何 Task 导致问题，回滚方式：

| Task | 回滚命令 |
|---|---|
| Task 1 | `git revert <commit>` 恢复文件，或手动从 `tsconfig.json` exclude 中移除 |
| Task 2 | `git revert <commit>`，恢复 `package.json` 和 `copy-assets.mjs` |
| Task 3-5 | `git revert <commit>`，恢复 `tsconfig.json` 和源文件 |
| Task 6 | `git revert <commit>`，恢复 `eslint.config.mjs` |

紧急回滚所有改动：
```bash
git reset --hard main
```
