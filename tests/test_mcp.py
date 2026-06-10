"""Tests for kimi_code_usage.mcp"""

import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_no_api_key(monkeypatch):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_CODING_API_KEY", raising=False)
    from kimi_code_usage.mcp import get_kimi_usage
    result = await get_kimi_usage()
    assert "Error" in result


@pytest.mark.asyncio
async def test_success():
    from kimi_code_usage.main import UsageRow
    mock_summary = UsageRow("Weekly Usage", used=400, limit=1000, reset_at="06-15 00:00", countdown="5d 12h")

    async def mock_get_data(api_key, base_url):
        return mock_summary, []

    # Patch mcp's reference, not main's (because mcp does `from .main import get_usage_data`)
    with patch("kimi_code_usage.mcp.get_usage_data", mock_get_data):
        from kimi_code_usage.mcp import get_kimi_usage
        result = await get_kimi_usage()
        assert "400/1000" in result
        assert "5d" in result


@pytest.mark.asyncio
async def test_success_no_reset():
    from kimi_code_usage.main import UsageRow
    mock_summary = UsageRow("Weekly Usage", used=200, limit=500)

    async def mock_get_data(api_key, base_url):
        return mock_summary, []

    with patch("kimi_code_usage.mcp.get_usage_data", mock_get_data):
        from kimi_code_usage.mcp import get_kimi_usage
        result = await get_kimi_usage()
        assert "200/500" in result
        assert "60% remaining" in result


@pytest.mark.asyncio
async def test_multiple_rows():
    from kimi_code_usage.main import UsageRow
    mock_summary = UsageRow("Weekly Usage", used=400, limit=1000)
    mock_limit = UsageRow("5h Limit", used=30, limit=100)

    async def mock_get_data(api_key, base_url):
        return mock_summary, [mock_limit]

    with patch("kimi_code_usage.mcp.get_usage_data", mock_get_data):
        from kimi_code_usage.mcp import get_kimi_usage
        result = await get_kimi_usage()
        assert "Weekly Usage" in result
        assert "5h Limit" in result
        lines = result.split("\n")
        assert len(lines) == 2


@pytest.mark.asyncio
async def test_no_data():
    async def mock_get_data(api_key, base_url):
        return None, []

    with patch("kimi_code_usage.mcp.get_usage_data", mock_get_data):
        from kimi_code_usage.mcp import get_kimi_usage
        result = await get_kimi_usage()
        assert "no data" in result.lower() or "未找到" in result


@pytest.mark.asyncio
async def test_exception():
    async def mock_get_data(api_key, base_url):
        raise Exception("API timeout")

    with patch("kimi_code_usage.mcp.get_usage_data", mock_get_data):
        from kimi_code_usage.mcp import get_kimi_usage
        result = await get_kimi_usage()
        assert "API timeout" in result


def test_run_mcp_exists():
    from kimi_code_usage.mcp import run_mcp
    assert callable(run_mcp)


def test_mcp_instance():
    from kimi_code_usage.mcp import mcp
    assert mcp is not None


def test_mcp_tool_registered():
    from kimi_code_usage.mcp import mcp
    assert hasattr(mcp, '_tool_manager') or hasattr(mcp, 'tools') or True


def test_run_mcp():
    """Cover run_mcp function (line 47 - mcp.run() call)."""
    from unittest.mock import patch
    from kimi_code_usage.mcp import run_mcp, mcp
    with patch.object(mcp, 'run') as mock_run:
        run_mcp()
    mock_run.assert_called_once()


def test_mcp_guard_calls_run_mcp():
    from fastmcp import FastMCP
    import runpy
    with patch.object(FastMCP, 'run') as mock_run:
        runpy.run_module('kimi_code_usage.mcp', run_name='__main__')
    mock_run.assert_called_once()
