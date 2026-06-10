import json
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta, timezone
from kimi_code_usage.providers.kimi import (
    _to_int,
    _get_reset_info,
    _limit_label,
    _to_usage_row,
    _parse_usage_payload,
    fetch_kimi_usage,
)

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
    assert _to_int(val) == expected

# -- _get_reset_info --
@pytest.mark.parametrize("key", ["resetTime", "reset_at", "reset_time"])
def test_get_reset_info_iso_string(key):
    future = datetime.now(timezone.utc) + timedelta(hours=25, minutes=30)
    result = _get_reset_info({key: future.isoformat()})
    assert result is not None
    _, countdown = result
    assert "1d" in countdown or "25h" in countdown

def test_get_reset_info_timestamp():
    future_ts = datetime.now().timestamp() + 7200
    result = _get_reset_info({"resetTime": future_ts})
    assert result is not None
    _, countdown = result
    assert "h" in countdown

def test_get_reset_info_reset_in():
    result = _get_reset_info({"reset_in": 3600})
    assert result is not None
    _, countdown = result
    assert "h" in countdown

def test_get_reset_info_expired():
    past_ts = datetime.now().timestamp() - 3600
    result = _get_reset_info({"resetTime": past_ts})
    assert result is not None
    _, countdown = result
    assert countdown == "0m"

def test_get_reset_info_none():
    assert _get_reset_info({}) is None

def test_get_reset_info_bad_date():
    assert _get_reset_info({"resetTime": "not-a-date"}) is None

# -- _limit_label --
def test_limit_label_hour():
    label = _limit_label({"duration": 5, "time_unit": "HOUR"}, 0)
    assert "5h" in label

def test_limit_label_day():
    label = _limit_label({"duration": 3, "time_unit": "DAY"}, 1)
    assert "3d" in label

def test_limit_label_fallback():
    label = _limit_label({}, 2)
    assert "#3" in label

# -- _to_usage_row --
def test_to_usage_row_full():
    row = _to_usage_row({"name": "test", "limit": 100, "used": 30}, default_label="Default")
    assert row is not None
    assert row.label == "test"
    assert row.used == 30
    assert row.limit == 100

def test_to_usage_row_from_remaining():
    row = _to_usage_row({"name": "x", "limit": 100, "remaining": 70}, default_label="Default")
    assert row is not None
    assert row.used == 30

def test_to_usage_row_none():
    assert _to_usage_row({"foo": "bar"}, default_label="Default") is None

# -- _parse_usage_payload --
def test_parse_usage_payload_data_list():
    payload = {
        "data": [
            {"model_name": "all", "limit": 1000, "used": 500},
            {"model_name": "gpt-4", "limit": 100, "used": 30},
            "not_mapping_should_be_skipped"
        ]
    }
    summary, limits = _parse_usage_payload(payload)
    assert summary is not None
    assert summary.used == 500
    assert len(limits) == 1

def test_parse_usage_payload_complex():
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
    summary, limits = _parse_usage_payload({})
    assert summary is None
    assert limits == []

def test_parse_usage_payload_bad_limit_items():
    payload = {"limits": [{"detail": {"limit": 10, "used": 5}}, "not_mapping", None]}
    summary, limits = _parse_usage_payload(payload)
    assert summary is None
    assert len(limits) == 1

# -- fetch_kimi_usage (async) --
@pytest.mark.asyncio
async def test_fetch_kimi_usage_success():
    async def mock_impl(*a, **kw):
        return {"data": [{"model_name": "all", "limit": 1000, "used": 400}]}

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_cm.status = 200
    mock_cm.json = mock_impl

    mock_session = AsyncMock()
    mock_session.get = lambda *a, **kw: mock_cm
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        res = await fetch_kimi_usage("test-key", "https://api.example.com/v1")
        assert len(res) == 1
        r = res[0]
        assert r.provider == "kimi"
        assert r.used == 400.0
        assert r.limit == 1000.0
        assert r.remaining == 600.0
        assert r.percent == 40.0
        assert r.unit == "%"

@pytest.mark.asyncio
async def test_fetch_kimi_usage_fallback():
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
        res = await fetch_kimi_usage("test-key", "https://api.example.com/v1")
        assert len(res) == 1
        assert res[0].used == 200.0

@pytest.mark.asyncio
async def test_fetch_kimi_usage_fallback_fails():
    def make_cm(status):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = status
        if status == 500:
            cm.text = AsyncMock(return_value="Internal error")
        return cm

    mock_session = AsyncMock()
    mock_session.get = lambda *a, **kw: make_cm(500)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_kimi_usage("test-key", "https://api.example.com/v1")
        assert "500" in str(exc.value)
