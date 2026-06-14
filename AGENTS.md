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

### 4. 验证

```bash
uv run -- python -c "import urllib.request, json; print(json.load(urllib.request.urlopen('https://pypi.org/pypi/kimi-code-usage/json'))['info']['version'])"
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

## 测试与覆盖率

- 运行全部测试：`uv run pytest`
- 带覆盖率检查：`uv run pytest --cov=kimi_code_usage --cov-report=term-missing`
- 目标覆盖率：100%

## Git 工作流

- 使用 `git-feature` skill 创建功能分支
- 按文件粒度提交，遵循 conventional commits
- 通过 PR 合并到 `main`
- 合并后删除本地和远程 feature 分支
