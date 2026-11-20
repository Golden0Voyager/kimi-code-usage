from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from kimi_code_usage.providers import ProviderUsage
from kimi_code_usage.providers.kimi import (
    _get_reset_info,
    _kimi_error_hint,
    _limit_label,
    _parse_usage_payload,
    _to_int,
    _to_usage_row,
    fetch_kimi_usage,
)
from kimi_code_usage.providers.kimi_membership import MonthlyUsageUnavailable


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

def test_kimi_error_hint_404_explains_usage_endpoint_configuration():
    hint = _kimi_error_hint(404, zh=False)
    assert "usage endpoint" in hint
    assert "https://api.kimi.com/coding/v1" in hint
    assert "api.moonshot.cn" in hint
    assert "sk-kimi" in hint

# -- _get_reset_info --
@pytest.mark.parametrize("key", ["resetTime", "reset_at", "reset_time"])
def test_get_reset_info_iso_string(key):
    future = datetime.now(UTC) + timedelta(hours=25, minutes=30)
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

# -- _window_minutes --
@pytest.mark.parametrize(
    "window,expected",
    [
        ({"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"}, 300.0),
        ({"duration": 2, "timeUnit": "TIME_UNIT_HOUR"}, 120.0),
        ({"duration": 2, "timeUnit": "TIME_UNIT_DAY"}, 2880.0),
        ({"duration": 1, "timeUnit": "TIME_UNIT_MONTH"}, 43200.0),
        ({"duration": 300}, 5.0),  # 无单位 → 与 _limit_label 的"秒"约定一致
        ({"duration": "bad", "timeUnit": "TIME_UNIT_MINUTE"}, None),
        ("nope", None),
        (None, None),
    ],
)
def test_window_minutes(window, expected):
    from kimi_code_usage.providers.kimi import _window_minutes

    assert _window_minutes(window) == expected

# -- _ratio_usage_row --
@pytest.mark.parametrize("entry", ["nope", None, [1, 2]])
def test_ratio_usage_row_returns_none_for_non_mapping_entry(entry):
    from kimi_code_usage.providers.kimi import _ratio_usage_row

    assert _ratio_usage_row(entry, "5h Limit") is None


def test_ratio_usage_row_returns_none_without_numeric_ratio():
    from kimi_code_usage.providers.kimi import _ratio_usage_row

    assert _ratio_usage_row({"used_ratio": "half"}, "5h Limit") is None

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


def test_parse_usage_payload_falls_back_to_usages_windows():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    payload = {
        "usages": {
            "limit_5h": {"used_ratio": 0, "reset_time": "2026-10-19T15:00:00Z"},
            "limit_7d": {"used_ratio": 0.1631, "reset_time": "2026-10-26T00:00:00Z"},
        }
    }
    summary, limits = _parse_usage_payload(payload)

    assert summary is not None and summary.label == "Weekly Usage"
    assert summary.used == 16 and summary.limit == 100          # 0.1631 → 16%
    assert [r.label for r in limits] == ["5h Limit"]            # 周条已由 summary 覆盖，不重复
    assert limits[0].used == 0 and limits[0].limit == 100


def test_parse_usage_payload_ignores_usages_when_usage_and_limits_present():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    # live 形状（E1/E2）：两套来源同时存在 → 不得重复出行
    payload = {
        "usage": {"limit": "100", "remaining": "84", "resetTime": "2026-10-26T00:00:00Z"},
        "limits": [
            {
                "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "remaining": "100", "resetTime": "2026-10-19T15:00:00Z"},
            }
        ],
        "usages": {
            "limit_5h": {"used_ratio": 0, "reset_time": "2026-10-19T15:00:00Z"},
            "limit_7d": {"used_ratio": 0.1631, "reset_time": "2026-10-26T00:00:00Z"},
        },
    }
    summary, limits = _parse_usage_payload(payload)

    assert summary is not None and summary.label == "Weekly Usage"
    assert summary.used == 16 and summary.limit == 100
    assert [r.label for r in limits] == ["5h Limit"]            # 恰好一行，无重复
    assert limits[0].used == 0


def test_parse_usage_payload_usages_clamps_out_of_range_ratio():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    summary, limits = _parse_usage_payload({"usages": {"limit_7d": {"used_ratio": 3.5}}})

    assert summary is not None
    assert summary.used == 100 and summary.limit == 100


def test_parse_usage_payload_skips_usages_without_ratio():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    summary, limits = _parse_usage_payload(
        {"usages": {"limit_5h": {"reset_time": "2026-10-19T15:00:00Z"}, "limit_7d": "nope"}}
    )

    assert summary is None
    assert limits == []


def test_parse_usage_payload_usages_fallback_survives_rowless_limit_window():
    from kimi_code_usage.providers.kimi import _parse_usage_payload

    payload = {
        "limits": [{"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"}, "detail": {}}],
        "usages": {"limit_5h": {"used_ratio": 0.5}},
    }
    summary, limits = _parse_usage_payload(payload)

    assert summary is None
    assert [(r.label, r.used, r.limit) for r in limits] == [("5h Limit", 50, 100)]


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

    with patch('aiohttp.ClientSession', return_value=mock_session), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=Exception("bridge unavailable")),
    ):
        res = await fetch_kimi_usage("test-key", "https://api.example.com/v1")
        assert len(res) == 2
        r = res[1]
        assert r.provider == "kimi"
        assert r.used == 400.0
        assert r.limit == 1000.0
        assert r.remaining == 600.0
        assert r.percent == 40.0
        assert r.unit == "%"


@pytest.mark.asyncio
async def test_fetch_kimi_usage_prepends_monthly_usage_and_preserves_api_rows():
    monthly = ProviderUsage("kimi", "Monthly Credits", 62.0, 100.0, 38.0, 62.0, "2026-08-12", "%")

    async def mock_json(*args, **kwargs):
        return {"data": [{"model_name": "all", "limit": 100, "used": 14}]}

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = mock_json
    session = AsyncMock()
    session.get = lambda *args, **kwargs: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(return_value=monthly),
    ):
        rows = await fetch_kimi_usage("test-key", "https://api.example.com/v1")

    assert [row.label for row in rows] == ["Monthly Credits", "all"]


@pytest.mark.asyncio
async def test_fetch_kimi_usage_keeps_api_rows_when_monthly_reader_is_unavailable():
    async def mock_json(*args, **kwargs):
        return {"data": [{"model_name": "all", "limit": 100, "used": 14}]}

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = mock_json
    session = AsyncMock()
    session.get = lambda *args, **kwargs: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    with patch("aiohttp.ClientSession", return_value=session), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=MonthlyUsageUnavailable("Kimi WebBridge is unavailable")),
    ):
        rows = await fetch_kimi_usage("test-key", "https://api.example.com/v1")

    assert rows[0].label == "Monthly Credits"
    assert rows[0].unit == "text"
    assert "WebBridge" in rows[0].text_value
    assert rows[1].label == "all"

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

    with patch('aiohttp.ClientSession', return_value=mock_session), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=Exception("bridge unavailable")),
    ):
        res = await fetch_kimi_usage("test-key", "https://api.example.com/v1")
        assert len(res) == 2
        assert res[1].used == 200.0

@pytest.mark.asyncio
async def test_fetch_kimi_usage_does_not_fallback_on_auth_error():
    calls = []

    def make_cm(status, text_data):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.status = status
        cm.text = AsyncMock(return_value=text_data)
        return cm

    def mock_get(url, *a, **kw):
        calls.append(url)
        if len(calls) == 1:
            return make_cm(401, '{"code":"unauthenticated"}')
        return make_cm(404, '{"error":{"message":"The requested resource was not found","type":"resource_not_found_error"}}')

    mock_session = AsyncMock()
    mock_session.get = mock_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        with pytest.raises(Exception) as exc:
            await fetch_kimi_usage("test-key", "https://api.example.com/v1")

    assert "401" in str(exc.value)
    assert "unauthenticated" in str(exc.value)
    assert "resource_not_found_error" not in str(exc.value)
    assert calls == ["https://api.example.com/v1/usages"]

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


def test_kimi_reset_info_short_delta():
    from kimi_code_usage.providers.kimi import _get_reset_info
    # delta is 30 minutes (1800s)
    future = datetime.now() + timedelta(seconds=1800)
    res = _get_reset_info({"resetTime": future.isoformat()})
    assert res is not None
    assert "m" in res[1] and "h" not in res[1] and "d" not in res[1]


def test_kimi_limit_label_monthly():
    from kimi_code_usage.providers.kimi import _limit_label
    res = _limit_label({"duration": 1, "time_unit": "MONTH"}, 0)
    assert res == "1mo Limit"

def test_kimi_limit_label_minute():
    from kimi_code_usage.providers.kimi import _limit_label
    # divisible by 60
    assert _limit_label({"duration": 300, "time_unit": "MINUTE"}, 0) == "5h Limit"
    # not divisible by 60
    assert _limit_label({"duration": 45, "time_unit": "MINUTE"}, 0) == "45m Limit"
    assert _limit_label({"duration": 45, "timeUnit": "MINUTE"}, 0) == "45m Limit"

def test_kimi_limit_label_second():
    from kimi_code_usage.providers.kimi import _limit_label
    assert _limit_label({"duration": 30, "time_unit": "SECOND"}, 0) == "30s Limit"



def test_kimi_parse_payload_empty_items():
    from kimi_code_usage.providers.kimi import _parse_usage_payload
    summary, limits = _parse_usage_payload({"data": [{"model_name": "kimi", "used": None, "limit": None}]})
    assert summary is None
    assert len(limits) == 0

    summary, limits = _parse_usage_payload({"limits": [{"detail": {"used": None, "limit": None}}]})
    assert summary is None
    assert len(limits) == 0


# -- _extra_usage_rows --
def test_extra_usage_rows_full_payload():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    payload = {
        "totalQuota": {"limit": "200", "used": "50"},
        "boosterWallet": {
            "status": "STATUS_ENABLED",
            "monthlyUsed": {"currency": "CNY", "priceInCents": "1234"},
            "monthlyChargeLimit": {"currency": "CNY", "priceInCents": "10000"},
        },
        "parallel": {"limit": "20"},
    }
    rows = _extra_usage_rows(payload, lang_zh=False)
    assert [r.label for r in rows] == ["Total Quota", "Extra Usage", "Parallel Limit"]

    quota, booster, parallel = rows
    assert quota.used == 50.0 and quota.limit == 200.0 and quota.percent == 25.0
    assert booster.used == 12.34 and booster.limit == 100.0 and booster.unit == "¥"
    assert parallel.unit == "text" and parallel.text_value == "20"


def test_extra_usage_rows_zh_labels():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows({"parallel": {"limit": 5}}, lang_zh=True)
    assert rows[0].label == "并发上限"


def test_extra_usage_rows_booster_disabled():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows({"boosterWallet": {"status": "STATUS_DISABLED"}}, lang_zh=False)
    assert len(rows) == 1
    assert rows[0].label == "Extra Usage"
    assert rows[0].text_value == "Not enabled"


def test_extra_usage_rows_booster_flag_enables_wallet():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {
                "status": "STATUS_DISABLED",
                "monthlyChargeLimitEnabled": True,
                "monthlyUsed": {"priceInCents": "500"},
                "monthlyChargeLimit": {"priceInCents": "10000"},
            }
        },
        lang_zh=False,
    )
    assert rows[0].unit == "¥"
    assert rows[0].used == 5.0
    assert rows[0].limit == 100.0


def test_extra_usage_rows_booster_balance_enables_wallet():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {
                "balance": {"type": "BOOSTER", "amount": 2500000},
                "monthlyUsed": {"priceInCents": "500"},
                "monthlyChargeLimit": {"priceInCents": "10000"},
            }
        },
        lang_zh=False,
    )
    assert rows[0].unit == "¥"
    assert rows[0].limit == 100.0


def test_extra_usage_rows_booster_balance_without_amount_stays_disabled():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    for balance in (
        {"type": "BOOSTER", "amount": 0},
        {"type": "OTHER", "amount": 9},
        {"type": "BOOSTER"},
    ):
        rows = _extra_usage_rows(
            {"booster_wallet": {"balance": balance, "monthlyUsed": {"priceInCents": "500"}}},
            lang_zh=False,
        )
        assert rows[0].text_value == "Not enabled"


def test_extra_usage_rows_booster_snake_case_flag_enables_wallet():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {
                "monthly_charge_limit_enabled": True,
                "monthlyUsed": {"priceInCents": "500"},
                "monthlyChargeLimit": {"priceInCents": "10000"},
            }
        },
        lang_zh=False,
    )
    assert rows[0].unit == "¥"
    assert rows[0].limit == 100.0


def test_extra_usage_rows_booster_active_without_amounts_is_silent():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    # 没有金额可报时不产生行（也不应误报"未开启"）
    assert _extra_usage_rows(
        {"booster_wallet": {"balance": {"type": "BOOSTER", "amount": 2500000}}}, lang_zh=False
    ) == []
    assert _extra_usage_rows({"booster_wallet": {"monthlyChargeLimitEnabled": True}}, lang_zh=False) == []
    assert _extra_usage_rows({"booster_wallet": {"status": "STATUS_ENABLED"}}, lang_zh=False) == []


def test_extra_usage_rows_booster_unlimited():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "boosterWallet": {
                "status": "STATUS_ENABLED",
                "monthlyUsed": {"priceInCents": "2500"},
                "monthlyChargeLimit": {"priceInCents": "0"},
            }
        },
        lang_zh=False,
    )
    assert rows[0].text_value == "¥25.00"
    assert rows[0].limit is None


def test_extra_usage_rows_empty_or_malformed():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    assert _extra_usage_rows({}, lang_zh=False) == []
    assert _extra_usage_rows({"totalQuota": {}}, lang_zh=False) == []
    assert _extra_usage_rows(
        {"parallel": {"limit": "abc"}, "boosterWallet": "nope"}, lang_zh=False
    ) == []


def test_extra_usage_rows_reads_snake_case_booster_wallet():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    # live 形状（E1/E3）：蛇形 key，priceInCents 是字符串
    payload = {
        "booster_wallet": {
            "status": "STATUS_DISABLED",
            "monthlyUsed": {"currency": "CNY", "priceInCents": "1234"},
            "monthlyChargeLimit": {"currency": "CNY", "priceInCents": "10000"},
        }
    }
    rows = _extra_usage_rows(payload, lang_zh=False)
    assert [r.label for r in rows] == ["Extra Usage"]
    assert rows[0].text_value == "Not enabled"


def test_extra_usage_rows_reads_snake_case_booster_wallet_enabled():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {
                "status": "STATUS_ENABLED",
                "monthlyUsed": {"currency": "CNY", "priceInCents": "1234"},
                "monthlyChargeLimit": {"currency": "CNY", "priceInCents": "10000"},
            }
        },
        lang_zh=False,
    )
    assert rows[0].label == "Extra Usage"
    assert rows[0].used == 12.34
    assert rows[0].limit == 100.0
    assert rows[0].unit == "¥"


def test_extra_usage_rows_snake_case_wins_over_camel_case():
    from kimi_code_usage.providers.kimi import _extra_usage_rows

    rows = _extra_usage_rows(
        {
            "booster_wallet": {"status": "STATUS_DISABLED"},
            "boosterWallet": {"status": "STATUS_ENABLED"},
        },
        lang_zh=False,
    )
    assert rows[0].text_value == "Not enabled"


@pytest.mark.asyncio
async def test_fetch_kimi_usage_appends_extra_rows():
    async def mock_json(*args, **kwargs):
        return {
            "usage": {"limit": "100", "used": "67"},
            "parallel": {"limit": "20"},
            "boosterWallet": {"status": "STATUS_DISABLED"},
        }

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = mock_json
    session = AsyncMock()
    session.get = lambda *args, **kwargs: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=Exception("bridge unavailable")),
    ):
        rows = await fetch_kimi_usage("test-key", "https://api.example.com/v1")

    labels = [r.label for r in rows]
    assert "Weekly Usage" in labels
    assert "Extra Usage" in labels
    assert "Parallel Limit" in labels


@pytest.mark.asyncio
async def test_monthly_usage_row_prefers_oauth_over_webbridge():
    from kimi_code_usage.providers.kimi import _monthly_usage_row

    oauth_row = ProviderUsage("kimi", "Monthly Credits", 1.0, 100.0, 99.0, 1.0, None, "%")
    with patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_oauth",
        new=AsyncMock(return_value=(oauth_row, "")),
    ), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=AssertionError("webbridge must not be called")),
    ):
        row = await _monthly_usage_row()

    assert row is oauth_row


@pytest.mark.asyncio
async def test_monthly_usage_row_falls_back_to_webbridge_when_oauth_has_no_data():
    from kimi_code_usage.providers.kimi import _monthly_usage_row

    webbridge_row = ProviderUsage("kimi", "Monthly Credits", 7.0, 100.0, 93.0, 7.0, None, "%")
    with patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_oauth",
        new=AsyncMock(return_value=(None, "response has no totalQuota")),
    ), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(return_value=webbridge_row),
    ):
        row = await _monthly_usage_row()

    assert row is webbridge_row


@pytest.mark.asyncio
async def test_monthly_usage_row_reports_both_sources_when_unavailable():
    from kimi_code_usage.providers.kimi import _monthly_usage_row

    with patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_oauth",
        new=AsyncMock(return_value=(None, "access token expired at 2026-09-29 13:45")),
    ), patch(
        "kimi_code_usage.providers.kimi.fetch_monthly_usage_from_webbridge",
        new=AsyncMock(side_effect=MonthlyUsageUnavailable("Kimi WebBridge daemon is not running.")),
    ):
        row = await _monthly_usage_row()

    assert row.unit == "text"
    assert "expired" in row.text_value
    assert "daemon is not running" in row.text_value
