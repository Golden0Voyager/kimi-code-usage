# Agent 协作指南

本文件记录本项目的开发流程、发布经验和常见陷阱，供后续 AI/人类协作者参考。

## 发布流程（Release Checklist）

### 1. 前置条件

- 所有变更已合并到 `main`
- 测试全部通过且覆盖率达到预期
- `pyproject.toml` 中的版本号已更新

### 2. 版本号与标签

```bash
rtk git add pyproject.toml
rtk git commit -m "chore: bump version to X.Y.Z

chore: 将版本号提升至 X.Y.Z"
rtk git tag vX.Y.Z
rtk git push origin main --tags
```

### 3. 构建与发布

```bash
# 清理旧版本构建产物
rm -f dist/kimi_code_usage-*

# 构建 sdist 和 wheel
uv build

# 发布到 PyPI
# 注意：uv publish 不会自动读取 ~/.pypirc，需要通过环境变量传入凭据
UV_PUBLISH_USERNAME=__token__ UV_PUBLISH_PASSWORD=<your-pypi-token> uv publish dist/*
```

### 4. 扩展发布

`vsce` 打包前必须重新编译：`out/` 被 gitignore，`package.json` 里的
`vscode:prepublish` 会在打包时自动执行 `npm run build`，不要用 `zip` 或
`--no-dependencies` 绕过它。

```bash
cd vscode-extension
npm ci
npx vsce package                      # 产物：kimi-code-usage-<version>.vsix
# 有 PAT 时可直接发；没有则到 Marketplace 网页上传同一个 vsix
npx vsce publish --packagePath kimi-code-usage-<version>.vsix -p "$VSCE_PAT"
```

网页上传后市场页面需要几分钟才可见（实测约 5 分钟），期间查询仍返回旧版本，不是失败。

### 5. 验证

```bash
# PyPI
uv run -- python -c "import urllib.request, json; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/kimi-code-usage/json'))['info']['version'])"

# Marketplace
curl -s -X POST "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery" \
  -H "Content-Type: application/json" -H "Accept: application/json;api-version=7.2-preview.1" \
  -d '{"filters":[{"criteria":[{"filterType":7,"value":"HainingYu.kimi-code-usage"}]}],"flags":914}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['results'][0]['extensions'][0]['versions'][0]['version'])"
```

## 已知陷阱

### uv publish 不读取 ~/.pypirc

`uv publish` 当前版本不会自动读取 `~/.pypirc` 中的用户名/密码配置。即使 `~/.pypirc` 已正确配置，也必须通过以下方式之一提供凭据：

- 环境变量：`UV_PUBLISH_USERNAME` 和 `UV_PUBLISH_PASSWORD`
- 命令行参数：`--username` 和 `--password`

### dist/ 目录残留旧版本

`uv build` 不会自动清理 `dist/` 中的旧文件。如果目录中存在旧版本（如 `0.1.2`）的 wheel/tar.gz，`uv publish dist/*` 会尝试上传这些旧文件并导致冲突。发布前务必清理：

```bash
rm -f dist/kimi_code_usage-*
```

### 版本号与 git tag 必须一致

PyPI 包版本来自 `pyproject.toml`，git tag 用于标记代码状态。两者应保持一致（如 `v0.1.3` 对应 `version = "0.1.3"`）。

### 在 worktree 里构建会把 node_modules 打进 sdist

hatchling 依赖 VCS 决定 sdist 内容，而 git worktree 里 `.git` 是个文件，检测失败后它退化为"打包所有未跟踪文件"。0.2.0 准备时 sdist 因此从 0.4 MB 涨到 49.7 MB，塞进 `vscode-extension/node_modules`（11,941 个文件）；同一份代码在主 checkout 构建只有 486 KB。`pyproject.toml` 已有显式 `[tool.hatch.build.targets.sdist] exclude`，新增需要排除的目录时同步维护，并在发布前抽查：

```bash
tar tzf dist/*.tar.gz | grep -c node_modules/   # 期望 0
```

### 发布后立刻验证 PyPI 版本可能命中索引缓存

上传成功后头几分钟，`uv pip install <pkg>==<新版本>` 可能报 "no version of ..."。这不是发布失败：uv 缓存了上传前的 simple 索引页，加 `--refresh` 或稍等即可。

### 扩展打包不能依赖机器上现成的 out/

`out/` 被 gitignore，`vsce package` 只会打包当前磁盘上的那份。`vscode:prepublish` 已确保先编译；发布前仍要核对包内版本号与内容：

```bash
unzip -p <vsix> extension/package.json | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>console.log(JSON.parse(s).version))"
```

## 测试与覆盖率

- 运行全部测试：`uv run pytest`
- 带覆盖率检查：`uv run pytest --cov=kimi_code_usage --cov-report=term-missing`
- 目标覆盖率：100%

## Git 工作流

- 使用 `git-feature` skill 创建功能分支
- 按文件粒度提交，遵循 conventional commits
- 通过 PR 合并到 `main`
- 合并后删除本地和远程 feature 分支
