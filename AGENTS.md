# Agent 协作指南

本文件记录本项目的发布流程与踩过的坑，供后续 AI/人类协作者参考。

Git 规范（一文件一 commit、conventional commits、PR 合入、合并后删分支）沿用
`/Code/AGENTS.md`，此处只写本项目特例。

## 发布流程

### 1. 前置条件

- 所有变更已合并到 `main`，工作区干净
- 测试通过、覆盖率达标（唯一阈值来源是 `pyproject.toml` 的 `fail_under`，当前 85）
- `pyproject.toml` **和 `uv.lock`** 里的项目版本都已更新

### 2. 版本与标签

`uv.lock` 会记录项目自身版本，而 CI 用 `uv export --frozen` 审计，不同步会直接失败。
只需改版本行，不必整份重新锁定：`uv lock --check` 应仍然通过。

```bash
git tag vX.Y.Z
git push origin vX.Y.Z      # 只推这一个 tag；不要用 --tags，那会推掉所有本地 tag
```

### 3. PyPI

```bash
rm -f dist/kimi_code_usage-*    # uv build 不清旧文件，残留会被一起上传
uv build
UV_PUBLISH_USERNAME=__token__ UV_PUBLISH_PASSWORD=<token> uv publish dist/*
```

`uv publish` 不读 `~/.pypirc`，凭据只能走环境变量或 `--username/--password`。

### 4. 扩展

`out/` 被 gitignore，`vscode:prepublish` 会在打包前自动 `npm run build`。不要用 `zip` 或
`--no-dependencies` 绕过它，否则发出去的是机器上现成的旧 JS。

```bash
cd vscode-extension && npm ci
npx vsce package                                            # kimi-code-usage-<version>.vsix
npx vsce publish --packagePath kimi-code-usage-<version>.vsix -p "$VSCE_PAT"
```

没有 PAT 时到 Marketplace 网页上传同一个 vsix 即可。市场页面约 5 分钟后才可见，期间查到旧
版本不是失败。

### 5. 验证

```bash
# PyPI
uv run -- python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/kimi-code-usage/json'))['info']['version'])"

# Marketplace
curl -s -X POST "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery" \
  -H "Content-Type: application/json" -H "Accept: application/json;api-version=7.2-preview.1" \
  -d '{"filters":[{"criteria":[{"filterType":7,"value":"HainingYu.kimi-code-usage"}]}],"flags":914}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['results'][0]['extensions'][0]['versions'][0]['version'])"
```

上传后头几分钟 `uv pip install <pkg>==<新版本>` 可能报 "no version"，那是索引缓存，加
`--refresh` 重试。

## 陷阱

### worktree 构建会把 node_modules 打进 sdist

hatchling 靠 VCS 决定 sdist 内容，而 worktree 里 `.git` 是个文件，检测失败后退化为"打包
所有未跟踪文件"：0.2.0 时 sdist 从 0.4 MB 涨到 49.7 MB（塞进 11,941 个 node_modules 文件），
同一份代码在主 checkout 只有 486 KB。`pyproject.toml` 已有
`[tool.hatch.build.targets.sdist] exclude`，新增发布目录时同步维护，发布前抽查：

```bash
tar tzf dist/*.tar.gz | grep -c node_modules/   # 期望 0
```

### 扩展包内容要核对

`vsce package` 打包的是磁盘上的 `out/`，包含范围由 `.vscodeignore` 决定。发布前确认包里
的版本号与内容确实是对的：

```bash
unzip -p <vsix> extension/package.json | node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>console.log(JSON.parse(s).version))"
```

## 测试

- 全部：`uv run pytest`
- 覆盖率：`uv run pytest --cov --cov-report=term-missing tests/`，再跑 `uv run coverage report`
- 阈值唯一来源是 `pyproject.toml` 的 `fail_under`（当前 85），实测约 95%
