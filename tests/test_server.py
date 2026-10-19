"""Behavioral tests for the aiohttp dashboard server.

Written against the real code paths: a real socket is bound and queried with a
real HTTP client, and the pure helpers are driven with real dataclasses. Only
the two genuine side effects (provider network calls, LAN IP discovery) are
stubbed.
"""

import asyncio
import contextlib
import json
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import aiohttp
import pytest
from aiohttp.test_utils import make_mocked_request

from kimi_code_usage import server
from kimi_code_usage.providers import ActivityTotals, DailyUsage, ModelUsage, ProviderUsage


def _addr(ip: str) -> tuple:
    """One getaddrinfo entry in the 5-tuple shape the stdlib returns."""
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))


def _raise_oserror(*_args, **_kwargs):
    raise OSError("name resolution unavailable")


def _fake_udp_socket(ip: str) -> MagicMock:
    """A socket usable as a context manager whose getsockname() reports `ip`."""
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.getsockname.return_value = (ip, 51234)
    return sock


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _usage_item(**overrides) -> ProviderUsage:
    fields = {
        "provider": "kimi",
        "label": "Weekly Usage",
        "used": 25.0,
        "limit": 100.0,
        "remaining": 75.0,
        "percent": 25.0,
        "reset_at": "2026-01-01 00:00",
        "unit": "%",
    }
    fields.update(overrides)
    return ProviderUsage(**fields)


# --- _get_lan_ip -----------------------------------------------------------


@pytest.mark.parametrize("ip", ["192.168.1.20", "10.0.0.7", "172.16.5.4"])
def test_get_lan_ip_returns_private_lan_address(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [_addr(ip)])

    assert server._get_lan_ip() == ip


def test_get_lan_ip_returns_first_non_loopback_when_no_private_subnet(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [_addr("127.0.0.1"), _addr("8.8.8.8")]
    )

    assert server._get_lan_ip() == "8.8.8.8"


def test_get_lan_ip_uses_dns_socket_when_hostname_lookup_fails(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _raise_oserror)
    monkeypatch.setattr(socket, "socket", MagicMock(return_value=_fake_udp_socket("172.20.10.3")))

    assert server._get_lan_ip() == "172.20.10.3"


def test_get_lan_ip_ignores_loopback_reported_by_dns_socket(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _raise_oserror)
    monkeypatch.setattr(socket, "socket", MagicMock(return_value=_fake_udp_socket("127.0.0.1")))

    assert server._get_lan_ip() == "127.0.0.1"


def test_get_lan_ip_falls_back_to_loopback_when_everything_fails(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _raise_oserror)
    monkeypatch.setattr(socket, "socket", _raise_oserror)

    assert server._get_lan_ip() == "127.0.0.1"


# --- _build_html -----------------------------------------------------------


def test_build_html_renders_english_dashboard():
    html = server._build_html(lang_zh=False)

    assert '<html lang="en">' in html
    assert "AI Quota Dashboard" in html
    assert "Show Providers" in html
    assert "{provider_order_json}" not in html
    assert json.dumps(server._PROVIDER_ORDER) in html


def test_build_html_renders_chinese_dashboard():
    html = server._build_html(lang_zh=True)

    assert '<html lang="zh">' in html
    assert "AI 用量配额看板" in html
    assert "显示提供商" in html
    assert "{provider_order_json}" not in html
    assert json.dumps(server._PROVIDER_ORDER) in html


# --- handle_index ----------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_index_switches_to_chinese_for_accept_language_header(monkeypatch):
    monkeypatch.setattr(server, "IS_ZH", False)
    request = make_mocked_request("GET", "/", headers={"Accept-Language": "zh-CN,zh;q=0.9"})

    response = await server.handle_index(request)

    assert response.content_type == "text/html"
    assert "AI 用量配额看板" in response.text


@pytest.mark.asyncio
async def test_handle_index_stays_english_for_english_accept_language(monkeypatch):
    monkeypatch.setattr(server, "IS_ZH", False)
    request = make_mocked_request("GET", "/", headers={"Accept-Language": "en-US,en;q=0.9"})

    response = await server.handle_index(request)

    assert "AI Quota Dashboard" in response.text


@pytest.mark.asyncio
async def test_handle_index_falls_back_to_module_locale(monkeypatch):
    monkeypatch.setattr(server, "IS_ZH", True)

    response = await server.handle_index(make_mocked_request("GET", "/"))

    assert "AI 用量配额看板" in response.text


@pytest.mark.asyncio
async def test_handle_index_cannot_force_english_when_locale_is_chinese(monkeypatch):
    # The module locale wins over the header: `... or IS_ZH` means a zh locale is
    # sticky, so a per-request English header cannot turn the dashboard English.
    monkeypatch.setattr(server, "IS_ZH", True)

    response = await server.handle_index(
        make_mocked_request("GET", "/", headers={"Accept-Language": "en-US,en;q=0.9"})
    )

    assert "AI 用量配额看板" in response.text


# --- _item_to_dict ---------------------------------------------------------


def test_item_to_dict_omits_optional_sections_when_absent():
    payload = server._item_to_dict(_usage_item(countdown="5d 12h", text_value=None))

    assert payload == {
        "label": "Weekly Usage",
        "used": 25.0,
        "limit": 100.0,
        "remaining": 75.0,
        "percent": 25.0,
        "unit": "%",
        "countdown": "5d 12h",
        "reset_at": "2026-01-01 00:00",
        "text_value": None,
    }


def test_item_to_dict_serialises_activity_daily_and_top_models():
    item = _usage_item(
        activity_totals=ActivityTotals(
            spend=1.5, requests=3.0, prompt_tokens=100.0, completion_tokens=20.0, reasoning_tokens=5.0
        ),
        daily_activity=[
            DailyUsage(
                date="2026-01-01",
                total=2.0,
                models=[
                    ModelUsage(
                        model="k2",
                        spend=2.0,
                        requests=1.0,
                        prompt_tokens=10.0,
                        completion_tokens=2.0,
                        reasoning_tokens=1.0,
                    )
                ],
            )
        ],
        top_models=[
            ModelUsage(
                model="k2",
                spend=1.0,
                requests=1.0,
                prompt_tokens=5.0,
                completion_tokens=1.0,
                reasoning_tokens=0.0,
            )
        ],
    )

    payload = server._item_to_dict(item)

    assert payload["activity_totals"] == {
        "spend": 1.5,
        "requests": 3.0,
        "prompt_tokens": 100.0,
        "completion_tokens": 20.0,
        "reasoning_tokens": 5.0,
    }
    assert payload["daily_activity"] == [
        {
            "date": "2026-01-01",
            "total": 2.0,
            "models": [
                {
                    "model": "k2",
                    "spend": 2.0,
                    "requests": 1.0,
                    "prompt_tokens": 10.0,
                    "completion_tokens": 2.0,
                    "reasoning_tokens": 1.0,
                }
            ],
        }
    ]
    assert payload["top_models"] == [
        {
            "model": "k2",
            "spend": 1.0,
            "requests": 1.0,
            "prompt_tokens": 5.0,
            "completion_tokens": 1.0,
            "reasoning_tokens": 0.0,
        }
    ]


# --- handle_api ------------------------------------------------------------


def _stub_resolver(config: object, seen: list):
    def resolve():
        seen.append(config)
        return config

    return lambda: SimpleNamespace(resolve=resolve)


@pytest.mark.asyncio
async def test_handle_api_serialises_results_and_errors(monkeypatch):
    config = object()
    seen: list = []

    async def fake_dispatch_all(received):
        assert received is config
        return {"kimi": [_usage_item()]}, {"openai": "Not configured"}

    monkeypatch.setattr(server, "ConfigResolver", _stub_resolver(config, seen))
    monkeypatch.setattr(server, "dispatch_all", fake_dispatch_all)

    response = await server.handle_api(make_mocked_request("GET", "/api/usage"))

    payload = json.loads(response.text)
    assert seen == [config]
    assert payload["results"]["kimi"][0]["label"] == "Weekly Usage"
    assert payload["results"]["kimi"][0]["percent"] == 25.0
    assert payload["errors"] == {"openai": "Not configured"}


@pytest.mark.asyncio
async def test_handle_api_returns_empty_payload_when_no_providers(monkeypatch):
    async def fake_dispatch_all(_received):
        return {}, {}

    monkeypatch.setattr(server, "ConfigResolver", _stub_resolver(object(), []))
    monkeypatch.setattr(server, "dispatch_all", fake_dispatch_all)

    response = await server.handle_api(make_mocked_request("GET", "/api/usage"))

    assert json.loads(response.text) == {"results": {}, "errors": {}}


# --- run_server ------------------------------------------------------------


async def _poll_get(session: aiohttp.ClientSession, url: str, attempts: int = 80) -> tuple[int, str]:
    """GET `url`, retrying while the server is still coming up."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            async with session.get(url) as response:
                return response.status, await response.text()
        except (aiohttp.ClientError, OSError) as exc:  # not listening yet
            last = exc
            await asyncio.sleep(0.05)
    raise AssertionError(f"server never became reachable: {last!r}")


@pytest.mark.asyncio
async def test_run_server_serves_dashboard_and_api_then_shuts_down(monkeypatch, capsys):
    monkeypatch.setattr(server, "IS_ZH", True)
    monkeypatch.setattr(server, "_get_lan_ip", lambda: "192.168.1.5")

    async def fake_dispatch_all(_received):
        return {"kimi": [_usage_item()]}, {}

    monkeypatch.setattr(server, "ConfigResolver", _stub_resolver(object(), []))
    monkeypatch.setattr(server, "dispatch_all", fake_dispatch_all)

    port = _free_port()
    task = asyncio.create_task(server.run_server(port=port, lang_zh=True))
    try:
        async with aiohttp.ClientSession() as session:
            status, html = await _poll_get(session, f"http://127.0.0.1:{port}/")
            assert status == 200
            assert "AI 用量配额看板" in html

            status, body = await _poll_get(session, f"http://127.0.0.1:{port}/api/usage")
            assert status == 200
            assert json.loads(body)["results"]["kimi"][0]["label"] == "Weekly Usage"
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert task.done()
    output = capsys.readouterr().out
    assert "启动成功" in output
    assert f"http://0.0.0.0:{port}" in output
    assert "http://192.168.1.5" in output
    assert "按 Ctrl-C 停止" in output


@pytest.mark.asyncio
async def test_run_server_prints_english_messages_when_not_chinese(monkeypatch, capsys):
    monkeypatch.setattr(server, "_get_lan_ip", lambda: "10.1.2.3")

    task = asyncio.create_task(server.run_server(port=_free_port(), lang_zh=False))
    try:
        await asyncio.sleep(0.1)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    output = capsys.readouterr().out
    assert "Server started" in output
    assert "LAN access: http://10.1.2.3" in output
    assert "Press Ctrl-C to stop" in output
