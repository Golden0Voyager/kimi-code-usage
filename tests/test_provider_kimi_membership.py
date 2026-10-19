from unittest.mock import AsyncMock, patch

import pytest

from kimi_code_usage.providers.kimi_membership import (
    MonthlyUsageUnavailable,
    _load_token_state,
    _webbridge_unavailable_message,
    fetch_monthly_usage_from_oauth,
    fetch_monthly_usage_from_webbridge,
    load_kimi_cli_access_token,
    parse_monthly_usage_snapshot,
)
from kimi_code_usage.providers.webbridge import WebBridgeStatus


def test_parse_monthly_usage_snapshot_reads_first_total_card_in_usage_progress():
    snapshot = {
        "tree": [[
            {"role": "heading", "name": "用量进度"},
            {"role": "StaticText", "name": "总使用量"},
            {"role": "StaticText", "name": "62%"},
            {"role": "StaticText", "name": "Kimi Code"},
            {"role": "StaticText", "name": "2026-08-12 后重置"},
            {"role": "heading", "name": "赠送额度"},
            {"role": "StaticText", "name": "总使用量"},
            {"role": "StaticText", "name": "100%"},
        ]]
    }

    row = parse_monthly_usage_snapshot(snapshot, lang_zh=False)

    assert row is not None
    assert row.label == "Monthly Credits"
    assert row.used == 62.0
    assert row.limit == 100.0
    assert row.remaining == 38.0
    assert row.percent == 62.0
    assert row.reset_at == "2026-08-12"
    assert row.unit == "%"


def test_parse_monthly_usage_snapshot_returns_none_without_usage_progress_card():
    snapshot = {"tree": [[{"role": "StaticText", "name": "账户"}]]}

    assert parse_monthly_usage_snapshot(snapshot, lang_zh=True) is None


@pytest.mark.asyncio
async def test_fetch_monthly_usage_requests_snapshot_after_reusing_subscription_tab():
    responses = [
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)) as command:
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)
    assert row.used == 25.0
    assert [call.args[0] for call in command.await_args_list] == ["find_tab", "snapshot"]


@pytest.mark.asyncio
async def test_fetch_monthly_usage_opens_and_closes_subscription_tab_when_missing():
    responses = [
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
        {"ok": True, "data": {"closed": True}},
    ]
    with patch(
        "kimi_code_usage.providers.kimi_membership._bridge_command",
        new=AsyncMock(side_effect=[MonthlyUsageUnavailable("no matching tab"), *responses]),
    ) as command:
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert row.used == 25.0
    assert [call.args[0] for call in command.await_args_list] == ["find_tab", "navigate", "snapshot", "close_tab"]


@pytest.mark.asyncio
async def test_fetch_monthly_usage_retries_empty_snapshot_after_navigation():
    responses = [
        {"ok": True, "data": {"success": False}},
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "StaticText", "name": "Loading"}]]}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
        {"ok": True, "data": {"closed": True}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)):
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert row.used == 25.0


@pytest.mark.asyncio
async def test_fetch_monthly_usage_waits_for_slow_subscription_card():
    loading = {
        "ok": True,
        "data": {"tree": [[{"role": "StaticText", "name": "Loading"}]]},
    }
    loaded = {
        "ok": True,
        "data": {
            "tree": [[
                {"role": "heading", "name": "Usage Progress"},
                {"role": "StaticText", "name": "Total Usage"},
                {"role": "StaticText", "name": "25%"},
            ]]
        },
    }
    responses = [
        {"ok": True, "data": {"success": True}},
        loading,
        loading,
        loading,
        loading,
        loaded,
    ]
    with (
        patch(
            "kimi_code_usage.providers.kimi_membership._bridge_command",
            new=AsyncMock(side_effect=responses),
        ),
        patch(
            "kimi_code_usage.providers.kimi_membership.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep,
    ):
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert row.used == 25.0
    assert sleep.await_count == 4


@pytest.mark.asyncio
async def test_fetch_monthly_usage_explains_disconnected_bridge():
    with patch(
        "kimi_code_usage.providers.kimi_membership._bridge_command",
        new=AsyncMock(side_effect=MonthlyUsageUnavailable("Kimi WebBridge is unavailable")),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="WebBridge"):
            await fetch_monthly_usage_from_webbridge(lang_zh=False)


@pytest.mark.parametrize(
    ("status", "start_error", "expected"),
    [
        (WebBridgeStatus(False, False, False), None, "not installed"),
        (WebBridgeStatus(True, False, False), None, "daemon is not running"),
        (WebBridgeStatus(True, False, False), "cannot bind", "cannot bind"),
        (
            WebBridgeStatus(True, True, False),
            None,
            "browser extension is not connected",
        ),
    ],
)
def test_webbridge_unavailable_message_distinguishes_local_states(
    status, start_error, expected
):
    with (
        patch(
            "kimi_code_usage.providers.kimi_membership.get_webbridge_status",
            return_value=status,
        ),
        patch(
            "kimi_code_usage.providers.kimi_membership.last_webbridge_start_error",
            return_value=start_error,
        ),
    ):
        assert expected in _webbridge_unavailable_message()


@pytest.mark.asyncio
async def test_fetch_monthly_usage_explains_logged_out_or_missing_page_data():
    responses = [
        {"ok": True, "data": {"success": True}},
        *[
            {"ok": True, "data": {"tree": [[{"name": "Sign in"}]]}}
            for _ in range(8)
        ],
    ]
    with patch(
        "kimi_code_usage.providers.kimi_membership._bridge_command",
        new=AsyncMock(side_effect=responses),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="log in"):
            await fetch_monthly_usage_from_webbridge(lang_zh=False)


# -- OAuth fallback for monthly usage --
def test_load_kimi_cli_access_token_reads_valid_token(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 9999999999}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    assert load_kimi_cli_access_token() == "abc"


def test_load_kimi_cli_access_token_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH",
        str(tmp_path / "nope.json"),
    )
    assert load_kimi_cli_access_token() is None


def test_load_kimi_cli_access_token_none_when_expired(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 1}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    assert load_kimi_cli_access_token() is None


@pytest.mark.asyncio
async def test_fetch_monthly_usage_from_oauth_returns_total_quota(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 9999999999}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )

    payload = {"totalQuota": {"limit": "100", "used": "62", "resetTime": "2026-09-01T00:00:00Z"}}

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = AsyncMock(return_value=payload)
    session = AsyncMock()
    session.get = lambda *a, **k: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=session):
        row, _reason = await fetch_monthly_usage_from_oauth(lang_zh=False)

    assert row is not None
    assert row.used == 62.0
    assert row.limit == 100.0
    assert row.percent == 62.0


@pytest.mark.asyncio
async def test_fetch_monthly_usage_from_oauth_falls_back_when_no_total_quota():
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    cm.json = AsyncMock(return_value={"usage": {"limit": "100", "used": "10"}, "totalQuota": {}})
    session = AsyncMock()
    session.get = lambda *a, **k: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH",
        "/nonexistent/path/kimi-code.json",
    ), patch("aiohttp.ClientSession", return_value=session):
        row, _reason = await fetch_monthly_usage_from_oauth(lang_zh=False)

    assert row is None


@pytest.mark.asyncio
async def test_fetch_monthly_usage_from_oauth_reports_missing_total_quota(tmp_path, monkeypatch):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 200
    # live 形状（E1）：coding API 永远没有 totalQuota
    cm.json = AsyncMock(return_value={"usage": {"limit": "100", "remaining": "84"}})
    session = AsyncMock()
    session.get = lambda *a, **k: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 9999999999}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = await fetch_monthly_usage_from_oauth(lang_zh=False)

    assert row is None
    assert "totalQuota" in reason


@pytest.mark.asyncio
async def test_fetch_monthly_usage_from_oauth_reports_http_status(tmp_path, monkeypatch):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = 401
    cm.json = AsyncMock(return_value={})
    session = AsyncMock()
    session.get = lambda *a, **k: cm
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 9999999999}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = await fetch_monthly_usage_from_oauth(lang_zh=False)

    assert row is None
    assert "401" in reason


def test_load_token_state_reports_expired_token(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"access_token": "abc", "expires_at": 1}')
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    token, reason = _load_token_state()
    assert token is None
    assert "expired" in reason


def test_load_token_state_reports_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH",
        str(tmp_path / "nope.json"),
    )
    token, reason = _load_token_state()
    assert token is None
    assert "no Kimi CLI credential file" in reason


def test_load_token_state_reports_unreadable_json(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text("{not json")
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    token, reason = _load_token_state()
    assert token is None
    assert "credential file is not readable JSON" in reason


def test_load_token_state_reports_missing_access_token(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    cred.write_text("{}")
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )
    token, reason = _load_token_state()
    assert token is None
    assert "credential file has no access_token" in reason


@pytest.mark.asyncio
async def test_fetch_monthly_usage_marks_web_bridge_source():
    responses = [
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "Usage Progress"}, {"role": "StaticText", "name": "Total Usage"}, {"role": "StaticText", "name": "25%"}]]}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)):
        row = await fetch_monthly_usage_from_webbridge(lang_zh=False)

    assert row.label == "Monthly Credits (web)"
    assert row.used == 25.0


@pytest.mark.asyncio
async def test_fetch_monthly_usage_marks_web_bridge_source_zh():
    responses = [
        {"ok": True, "data": {"success": True}},
        {"ok": True, "data": {"tree": [[{"role": "heading", "name": "用量进度"}, {"role": "StaticText", "name": "总使用量"}, {"role": "StaticText", "name": "25%"}]]}},
    ]
    with patch("kimi_code_usage.providers.kimi_membership._bridge_command", new=AsyncMock(side_effect=responses)):
        row = await fetch_monthly_usage_from_webbridge(lang_zh=True)

    assert row.label == "月度额度（网页）"
    assert row.used == 25.0
