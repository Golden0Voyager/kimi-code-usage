import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from kimi_code_usage.providers.kimi_membership import (
    MonthlyUsageUnavailable,
    _bridge_command,
    _flatten_names,
    _load_token_state,
    _to_int,
    _total_quota_reset_at,
    _webbridge_unavailable_message,
    fetch_monthly_usage_from_oauth,
    fetch_monthly_usage_from_webbridge,
    load_kimi_cli_access_token,
    parse_monthly_usage_snapshot,
)
from kimi_code_usage.providers.webbridge import WebBridgeStatus


def _mock_aiohttp_session(*, get=None, post=None):
    """Build an aiohttp.ClientSession stand-in whose ``get``/``post`` return async CMs."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    if get is not None:
        session.get = get
    if post is not None:
        session.post = post
    return session


def _response_cm(status, *, json_data=None):
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=cm)
    cm.__aexit__ = AsyncMock(return_value=None)
    cm.status = status
    cm.json = AsyncMock(return_value=json_data)
    return cm


def _recording_post(calls, response_cm):
    """``post`` that records its kwargs and hands back the given async context manager."""

    def post(*args, **kwargs):
        calls.append(kwargs)
        return response_cm

    return post


def _raising_post(exc):
    def post(*args, **kwargs):
        raise exc

    return post


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


# -- small helpers -----------------------------------------------------------


def test_to_int_returns_none_for_non_integer_input():
    assert _to_int("abc") is None
    assert _to_int(None) is None
    assert _to_int("") is None
    assert _to_int("1.5") is None


def test_flatten_names_ignores_non_mapping_leaves():
    assert _flatten_names(["plain string", 42, None]) == []


def test_total_quota_reset_at_formats_known_shapes():
    assert _total_quota_reset_at({}) is None
    assert _total_quota_reset_at({"resetTime": None}) is None
    assert _total_quota_reset_at({"resetTime": 1_788_000_000}) == "2026-08-29 10:40"
    assert _total_quota_reset_at({"reset_at": "2026-08-29T12:00:00Z"}) == "2026-08-29 12:00"
    assert _total_quota_reset_at({"reset_time": "not-a-date"}) is None


def test_webbridge_unavailable_message_prefers_status_detail():
    with (
        patch(
            "kimi_code_usage.providers.kimi_membership.get_webbridge_status",
            return_value=WebBridgeStatus(True, False, False, "socket refused"),
        ),
        patch(
            "kimi_code_usage.providers.kimi_membership.last_webbridge_start_error",
            return_value=None,
        ),
    ):
        assert _webbridge_unavailable_message() == "Kimi WebBridge status check failed: socket refused"


def test_webbridge_unavailable_message_when_bridge_is_up_without_detail():
    status = WebBridgeStatus(True, True, True, None)
    with (
        patch("kimi_code_usage.providers.kimi_membership.get_webbridge_status", return_value=status),
        patch(
            "kimi_code_usage.providers.kimi_membership.last_webbridge_start_error",
            return_value=None,
        ),
    ):
        assert _webbridge_unavailable_message() == "Kimi WebBridge command failed."


def test_webbridge_unavailable_message_when_bridge_is_up_with_detail():
    status = WebBridgeStatus(True, True, True, "extension vanished")
    with (
        patch("kimi_code_usage.providers.kimi_membership.get_webbridge_status", return_value=status),
        patch(
            "kimi_code_usage.providers.kimi_membership.last_webbridge_start_error",
            return_value=None,
        ),
    ):
        assert _webbridge_unavailable_message() == "extension vanished"


def test_parse_monthly_usage_snapshot_requires_total_usage_row():
    snapshot = {"tree": [[{"name": "用量进度"}, {"name": "Kimi Code"}]]}
    assert parse_monthly_usage_snapshot(snapshot, lang_zh=True) is None


def test_parse_monthly_usage_snapshot_requires_percentage_row():
    snapshot = {"tree": [[{"name": "用量进度"}, {"name": "总使用量"}, {"name": "暂无数据"}]]}
    assert parse_monthly_usage_snapshot(snapshot, lang_zh=True) is None


def _write_credentials(tmp_path, monkeypatch):
    cred = tmp_path / "credentials" / "kimi-code.json"
    cred.parent.mkdir(parents=True)
    expires_at = int(time.time()) + 86_400
    cred.write_text(json.dumps({"access_token": "abc", "expires_at": expires_at}))
    monkeypatch.setattr(
        "kimi_code_usage.providers.kimi_membership._KIMI_CLI_CREDENTIALS_PATH", str(cred)
    )


def _raising(exc):
    """A ``get``/``post`` that fails synchronously, like aiohttp before any I/O."""

    def call(*args, **kwargs):
        raise exc

    return call


def test_oauth_reports_client_error_as_reason(tmp_path, monkeypatch):
    _write_credentials(tmp_path, monkeypatch)
    session = _mock_aiohttp_session(get=_raising(aiohttp.ClientError("socket gone")))

    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = asyncio.run(fetch_monthly_usage_from_oauth(lang_zh=False))

    assert row is None
    assert reason == "request failed: socket gone"


def test_oauth_reports_timeout_as_reason(tmp_path, monkeypatch):
    _write_credentials(tmp_path, monkeypatch)
    session = _mock_aiohttp_session(get=_raising(TimeoutError()))

    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = asyncio.run(fetch_monthly_usage_from_oauth(lang_zh=False))

    assert row is None
    assert reason.startswith("request failed:")


def test_oauth_rejects_non_mapping_payload(tmp_path, monkeypatch):
    _write_credentials(tmp_path, monkeypatch)
    session = _mock_aiohttp_session(get=lambda *a, **k: _response_cm(200, json_data=[1, 2, 3]))

    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = asyncio.run(fetch_monthly_usage_from_oauth(lang_zh=False))

    assert row is None
    assert reason == "response has no totalQuota"


def test_oauth_rejects_total_quota_without_used(tmp_path, monkeypatch):
    _write_credentials(tmp_path, monkeypatch)
    session = _mock_aiohttp_session(get=lambda *a, **k: _response_cm(200, json_data={"totalQuota": {}}))

    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = asyncio.run(fetch_monthly_usage_from_oauth(lang_zh=False))

    assert row is None
    assert reason == "response has no totalQuota"


def test_oauth_rejects_total_quota_without_limit(tmp_path, monkeypatch):
    _write_credentials(tmp_path, monkeypatch)
    payload = {"totalQuota": {"used": "62"}}
    session = _mock_aiohttp_session(get=lambda *a, **k: _response_cm(200, json_data=payload))

    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = asyncio.run(fetch_monthly_usage_from_oauth(lang_zh=False))

    assert row is None
    assert reason == "response has no totalQuota"


def test_oauth_rejects_non_positive_total_quota_limit(tmp_path, monkeypatch):
    _write_credentials(tmp_path, monkeypatch)
    payload = {"totalQuota": {"used": "62", "limit": "0"}}
    session = _mock_aiohttp_session(get=lambda *a, **k: _response_cm(200, json_data=payload))

    with patch("aiohttp.ClientSession", return_value=session):
        row, reason = asyncio.run(fetch_monthly_usage_from_oauth(lang_zh=False))

    assert row is None
    assert reason == "response has no totalQuota"


def test_bridge_command_returns_parsed_payload():
    calls = []
    session = _mock_aiohttp_session(
        post=_recording_post(calls, _response_cm(200, json_data={"ok": True, "data": {"tree": []}}))
    )

    with patch("aiohttp.ClientSession", return_value=session):
        data = asyncio.run(_bridge_command("snapshot", {"tab": 1}))

    assert data == {"ok": True, "data": {"tree": []}}
    assert calls == [{"json": {"action": "snapshot", "args": {"tab": 1}, "session": "kimi-usage"}}]


def test_bridge_command_rejects_unsuccessful_payload():
    session = _mock_aiohttp_session(post=lambda *a, **k: _response_cm(200, json_data={"ok": False}))

    with (
        patch("aiohttp.ClientSession", return_value=session),
        patch(
            "kimi_code_usage.providers.kimi_membership._webbridge_unavailable_message",
            return_value="bridge says no",
        ),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="bridge says no"):
            asyncio.run(_bridge_command("snapshot", {}))


def test_bridge_command_rejects_non_mapping_payload():
    session = _mock_aiohttp_session(post=lambda *a, **k: _response_cm(200, json_data=["nope"]))

    with (
        patch("aiohttp.ClientSession", return_value=session),
        patch(
            "kimi_code_usage.providers.kimi_membership._webbridge_unavailable_message",
            return_value="bridge says no",
        ),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="bridge says no"):
            asyncio.run(_bridge_command("snapshot", {}))


def test_bridge_command_reports_http_failure():
    session = _mock_aiohttp_session(post=lambda *a, **k: _response_cm(500, json_data={}))

    with (
        patch("aiohttp.ClientSession", return_value=session),
        patch(
            "kimi_code_usage.providers.kimi_membership._webbridge_unavailable_message",
            return_value="bridge says no",
        ),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="bridge says no"):
            asyncio.run(_bridge_command("snapshot", {}))


def test_bridge_command_wraps_client_error():
    session = _mock_aiohttp_session(post=_raising(aiohttp.ClientError("socket gone")))

    with (
        patch("aiohttp.ClientSession", return_value=session),
        patch(
            "kimi_code_usage.providers.kimi_membership._webbridge_unavailable_message",
            return_value="bridge says no",
        ),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="bridge says no"):
            asyncio.run(_bridge_command("snapshot", {}))


def test_bridge_command_wraps_timeout():
    session = _mock_aiohttp_session(post=_raising(TimeoutError()))

    with (
        patch("aiohttp.ClientSession", return_value=session),
        patch(
            "kimi_code_usage.providers.kimi_membership._webbridge_unavailable_message",
            return_value="bridge says no",
        ),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="bridge says no"):
            asyncio.run(_bridge_command("snapshot", {}))
