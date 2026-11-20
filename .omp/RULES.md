# kimi_usage 项目硬规则

本文件是 sticky rule，每轮请求都会携带，不随对话变长而失效。

## pytest asyncio 装饰器会触发免费模型 403

本项目 `tests/` 里有 107 处 `@pytest.mark.asyncio`。

**百度免费模型**（如 `openrouter/baidu/ernie-5.5-flash-preview:free`）的内容过滤器会把
`@pytest.mark.asyncio` 误判为邮箱地址，脱敏成 `[EMAIL]`。脱敏后 tool call 的 JSON
结构被破坏，请求返回：

```
403 Request blocked by content filter:
Content filter redaction would produce invalid tool call arguments
```

### 输出时避免写这个装饰器

需要提到它时，改写成不含 `@` 开头的等价形式：

- 不写：`@pytest.mark.asyncio`
- 改写为：`pytest.mark.asyncio`
- 或改写为：`asyncio` 装饰器 / pytest-asyncio 的 mark
- 描述代码位置时用 `tests/test_xxx.py` 的行号，不贴整行

### 遇到 403 时

不要重试同一个请求，也不要自行切换模型。告知用户：

> 这个 403 是百度免费模型把 `@pytest.mark.asyncio` 当邮箱脱敏导致的，
> 换模型可解。

### 这条规则管不到什么

它只约束**模型输出**。用 `read` / `grep` 读测试文件时，工具结果里仍有
`@pytest.mark.asyncio` 原文，照样会触发 403 —— 那需要换模型，规则无法规避。

## 测试命令

- 全部：`uv run pytest`
- 覆盖率：`uv run pytest --cov --cov-report=term-missing tests/`，再跑 `uv run coverage report`
- 阈值唯一来源是 `pyproject.toml` 的 `fail_under`（当前 85）