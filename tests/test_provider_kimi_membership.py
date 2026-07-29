from unittest.mock import AsyncMock, patch

import pytest

from kimi_code_usage.providers.kimi_membership import (
    MonthlyUsageUnavailable,
    _webbridge_unavailable_message,
    fetch_monthly_usage_from_webbridge,
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
            for _ in range(3)
        ],
    ]
    with patch(
        "kimi_code_usage.providers.kimi_membership._bridge_command",
        new=AsyncMock(side_effect=responses),
    ):
        with pytest.raises(MonthlyUsageUnavailable, match="log in"):
            await fetch_monthly_usage_from_webbridge(lang_zh=False)
