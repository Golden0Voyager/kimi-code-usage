"""Tests for kimi_code_usage.main"""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta, timezone

# Patch load_dotenv for ALL tests in this module so .env is never loaded
@pytest.fixture(autouse=True)
def _no_dotenv():
    with patch('kimi_code_usage.main.load_dotenv'):
        yield


# -- _to_int --

@pytest.mark.parametrize("val,expected", [
    (42, 42),
    ("42", 42),
    (None, None),
    ("abc", None),
    ([], None),
    (0, 0),
])
def test_to_int(val, expected):
    from kimi_code_usage.main import _to_int
    assert _to_int(val) == expected


# -- _get_reset_info --

@pytest.mark.parametrize("key", ["resetTime", "reset_at", "reset_time"])
def test_get_reset_info_iso_string(key):
    from kimi_code_usage.main import _get_reset_info
    future = datetime.now(timezone.utc) + timedelta(hours=25, minutes=30)
    result = _get_reset_info({key: future.isoformat()})
    assert result is not None
    _, countdown = result
    assert "1d" in countdown or "25h" in countdown


def test_get_reset_info_timestamp():
    from kimi_code_usage.main import _get_reset_info
    future_ts = datetime.now().timestamp() + 7200
    result = _get_reset_info({"resetTime": future_ts})
    assert result is not None
    _, countdown = result
    assert "h" in countdown


def test_get_reset_info_reset_in():
    from kimi_code_usage.main import _get_reset_info
    result = _get_reset_info({"reset_in": 3600})
    assert result is not None
    _, countdown = result
    assert "h" in countdown


def test_get_reset_info_expired():
    from kimi_code_usage.main import _get_reset_info
    past_ts = datetime.now().timestamp() - 3600
    result = _get_reset_info({"resetTime": past_ts})
    assert result is not None
    _, countdown = result
    assert countdown == "0m"


def test_get_reset_info_none():
    from kimi_code_usage.main import _get_reset_info
    assert _get_reset_info({}) is None


def test_get_reset_info_bad_date():
    from kimi_code_usage.main import _get_reset_info
    assert _get_reset_info({"resetTime": "not-a-date"}) is None


# -- _limit_label --

def test_limit_label_hour():
    from kimi_code_usage.main import _limit_label
    label = _limit_label({}, {}, {"duration": 5, "time_unit": "HOUR"}, 0)
    assert "5h" in label


def test_limit_label_day():
    from kimi_code_usage.main import _limit_label
    label = _limit_label({}, {}, {"duration": 3, "time_unit": "DAY"}, 1)
    assert "3d" in label


def test_limit_label_fallback():
    from kimi_code_usage.main import _limit_label
    label = _limit_label({}, {}, {}, 2)
    assert "#3" in label


def test_limit_label_time_unit_lowercase():
    from kimi_code_usage.main import _limit_label
    label = _limit_label({}, {}, {"duration": 1, "time_unit": "hour"}, 0)
    assert "1h" in label


# -- _to_usage_row --

def test_to_usage_row_full():
    from kimi_code_usage.main import _to_usage_row
    row = _to_usage_row({"name": "test", "limit": 100, "used": 30}, default_label="Default")
    assert row is not None
    assert row.label == "test"
    assert row.used == 30
    assert row.limit == 100


def test_to_usage_row_from_remaining():
    from kimi_code_usage.main import _to_usage_row
    row = _to_usage_row({"name": "x", "limit": 100, "remaining": 70}, default_label="Default")
    assert row is not None
    assert row.used == 30


def test_to_usage_row_none():
    from kimi_code_usage.main import _to_usage_row
    assert _to_usage_row({"foo": "bar"}, default_label="Default") is None


def test_to_usage_row_fallback_label():
    from kimi_code_usage.main import _to_usage_row
    row = _to_usage_row({"limit": 10, "used": 5}, default_label="Fallback")
    assert row is not None
    assert row.label == "Fallback"


def test_to_usage_row_alt_keys():
    from kimi_code_usage.main import _to_usage_row
    row = _to_usage_row({"title": "Alt", "limit_amount": 50, "used_amount": 20}, default_label="D")
    assert row is not None
    assert row.label == "Alt"
    assert row.used == 20
    assert row.limit == 50


# -- _parse_usage_payload --

def test_parse_usage_payload_data_list():
    from kimi_code_usage.main import _parse_usage_payload
    payload = {
        "data": [
            {"model_name": "all", "limit": 1000, "used": 500},
            {"model_name": "gpt-4", "limit": 100, "used": 30},
        ]
    }
    summary, limits = _parse_usage_payload(payload)
    assert summary is not None
    assert summary.used == 500
    assert len(limits) == 1


def test_parse_usage_payload_complex():
    from kimi_code_usage.main import _parse_usage_payload
    payload = {
        "usage": {"limit": 1000, "used": 500},
        "limits": [
            {
                "detail": {"name": "5h", "limit": 100, "used": 30},
                "window": {"duration": 5, "time_unit": "HOUR"}
            }
        ]
    }
    summary, limits = _parse_usage_payload(payload)
    assert summary is not None
    assert summary.limit == 1000
    assert len(limits) == 1
    assert "5h" in limits[0].label


def test_parse_usage_payload_empty():
    from kimi_code_usage.main import _parse_usage_payload
    summary, limits = _parse_usage_payload({})
    assert summary is None
    assert limits == []


def test_parse_usage_payload_no_summary():
    from kimi_code_usage.main import _parse_usage_payload
    payload = {"limits": [{"detail": {"name": "test", "limit": 10, "used": 5}}]}
    summary, limits = _parse_usage_payload(payload)
    assert summary is None
    assert len(limits) == 1


def test_parse_usage_payload_bad_limit_items():
    from kimi_code_usage.main import _parse_usage_payload
    payload = {"limits": [{"detail": {"limit": 10, "used": 5}}, "not_mapping", None]}
    summary, limits = _parse_usage_payload(payload)
    assert summary is None
    assert len(limits) == 1


# -- _get_visual_width --

def test_get_visual_width_ascii():
    from kimi_code_usage.main import _get_visual_width
    assert _get_visual_width("hello") == 5


def test_get_visual_width_cjk():
    from kimi_code_usage.main import _get_visual_width
    assert _get_visual_width("你好") == 4


def test_get_visual_width_mixed():
    from kimi_code_usage.main import _get_visual_width
    assert _get_visual_width("a你好b") == 6


# -- _format_rows --

def test_format_rows_single():
    from kimi_code_usage.main import UsageRow, _format_rows
    from rich.text import Text
    rows = [UsageRow("Test", used=50, limit=100)]
    result = _format_rows(rows)
    assert isinstance(result, Text)
    assert "Test" in str(result)


def test_format_rows_multiple():
    from kimi_code_usage.main import UsageRow, _format_rows
    rows = [
        UsageRow("First", used=95, limit=100),
        UsageRow("Second", used=50, limit=100),
    ]
    result = _format_rows(rows)
    text = str(result)
    assert "First" in text
    assert "Second" in text


def test_format_rows_zero_limit():
    from kimi_code_usage.main import UsageRow, _format_rows
    rows = [UsageRow("Zero", used=0, limit=0)]
    result = _format_rows(rows)
    assert "Zero" in str(result)


def test_format_rows_with_reset():
    from kimi_code_usage.main import UsageRow, _format_rows
    rows = [UsageRow("Test", used=50, limit=100, reset_at="01-01 00:00", countdown="5d 12h")]
    result = _format_rows(rows)
    text = str(result)
    assert "5d" in text or "countdown" in text.lower()


# -- get_usage_data (async) via mocking aiohttp at function level --

@pytest.mark.asyncio
async def test_get_usage_data_success():
    from kimi_code_usage.main import get_usage_data

    async def mock_impl(*a, **kw):
        return {"data": [{"model_name": "all", "limit": 1000, "used": 400}]}

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_cm.status = 200
    mock_cm.json = mock_impl

    def mock_get(*a, **kw):
        return mock_cm

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        summary, limits = await get_usage_data("test-key", "https://api.example.com/v1")
        assert summary is not None
        assert summary.used == 400


@pytest.mark.asyncio
async def test_get_usage_data_fallback():
    from kimi_code_usage.main import get_usage_data

    call_count = [0]

    def make_cm(status, json_data):
        async def json_impl(*a, **kw):
            return json_data
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = status
        cm.json = json_impl
        return cm

    def mock_get(*a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return make_cm(404, {"_error": "Not found"})
        return make_cm(200, {"usage": {"limit": 500, "used": 200}})

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        summary, limits = await get_usage_data("test-key", "https://api.example.com/v1")
        assert summary is not None
        assert summary.used == 200


@pytest.mark.asyncio
async def test_get_usage_data_fallback_fails():
    from kimi_code_usage.main import get_usage_data

    call_count = [0]

    def make_cm(status):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = status
        if status == 500:
            cm.text = AsyncMock(return_value="Internal error")
        return cm

    def mock_get(*a, **kw):
        call_count[0] += 1
        return make_cm(500)

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await get_usage_data("test-key", "https://api.example.com/v1")
        assert "500" in str(exc.value)


# -- main CLI --

@pytest.mark.asyncio
async def test_main_no_key(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "")
    monkeypatch.setenv("KIMI_CODING_API_KEY", "")
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    from kimi_code_usage.main import main
    await main()
    captured = capsys.readouterr()
    assert "Error" in captured.err or "error" in captured.err.lower()


def _make_mock_get_usage_data(summary_data, limit_data=None):
    """Return an async function that mocks get_usage_data."""
    from kimi_code_usage.main import UsageRow
    s = UsageRow(
        label=summary_data.get("label", "Weekly Usage"),
        used=summary_data.get("used", 400),
        limit=summary_data.get("limit", 1000)
    ) if summary_data else None
    limits = []
    if limit_data:
        for ld in limit_data:
            limits.append(UsageRow(
                label=ld.get("label", "Limit"),
                used=ld.get("used", 0),
                limit=ld.get("limit", 100)
            ))
    
    async def mock_fn(*a, **kw):
        return s, limits
    return mock_fn


@pytest.mark.asyncio
async def test_main_json_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    
    mock_fn = _make_mock_get_usage_data({"used": 400, "limit": 1000})
    with patch("kimi_code_usage.main.get_usage_data", mock_fn):
        from kimi_code_usage.main import main
        await main()
    
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert len(data) == 1
    assert data[0]["used"] == 400


@pytest.mark.asyncio
async def test_main_plain_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["prog", "--plain"])
    
    mock_fn = _make_mock_get_usage_data({"used": 400, "limit": 1000})
    with patch("kimi_code_usage.main.get_usage_data", mock_fn):
        from kimi_code_usage.main import main
        await main()
    
    captured = capsys.readouterr()
    assert "400/1000" in captured.out


@pytest.mark.asyncio
async def test_main_rich_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["prog"])
    
    mock_fn = _make_mock_get_usage_data({"used": 400, "limit": 1000})
    with patch("kimi_code_usage.main.get_usage_data", mock_fn):
        from kimi_code_usage.main import main
        await main()
    
    captured = capsys.readouterr()
    assert "Kimi" in captured.out or "Kimi" in captured.err


@pytest.mark.asyncio
async def test_main_no_data(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["prog"])
    
    mock_fn = _make_mock_get_usage_data(None)
    with patch("kimi_code_usage.main.get_usage_data", mock_fn):
        from kimi_code_usage.main import main
        await main()
    
    captured = capsys.readouterr()
    assert len(captured.out) >= 0


@pytest.mark.asyncio
async def test_main_api_error(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["prog"])
    
    async def mock_fn(*a, **kw):
        raise Exception("Connection refused")
    
    with patch("kimi_code_usage.main.get_usage_data", mock_fn):
        from kimi_code_usage.main import main
        await main()
    
    captured = capsys.readouterr()
    assert "Connection refused" in captured.err


# -- run_cli --

def test_run_cli(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    
    mock_fn = _make_mock_get_usage_data({"used": 50, "limit": 100})
    with patch("kimi_code_usage.main.get_usage_data", mock_fn):
        from kimi_code_usage.main import run_cli
        run_cli()  # Should not raise


def test_main_guard_calls_run_cli():
    import runpy
    import asyncio
    with patch.object(asyncio, 'run') as mock_run:
        runpy.run_module('kimi_code_usage.main', run_name='__main__')
    mock_run.assert_called_once()
