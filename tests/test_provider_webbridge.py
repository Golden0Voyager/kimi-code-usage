import json
import subprocess
from unittest.mock import patch

import pytest

from kimi_code_usage.providers.webbridge import (
    WebBridgeLifecycleError,
    WebBridgeStatus,
    get_webbridge_status,
    last_webbridge_start_error,
    start_webbridge,
)


def _completed(stdout: str, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(["kimi-webbridge"], returncode, stdout, stderr)


def test_status_reports_missing_binary(tmp_path):
    with patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", tmp_path / "missing"):
        assert get_webbridge_status() == WebBridgeStatus(
            installed=False,
            running=False,
            extension_connected=False,
        )


def test_status_parses_daemon_and_extension(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    payload = {"running": True, "extension_connected": True}
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed(json.dumps(payload)),
        ) as run,
    ):
        status = get_webbridge_status()
    assert status == WebBridgeStatus(True, True, True)
    assert run.call_args.args[0] == [str(binary), "status"]
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize(
    ("completed", "detail"),
    [
        (_completed("", returncode=1, stderr="status failed"), "status failed"),
        (_completed("not-json"), "invalid status response"),
        (_completed("[]"), "invalid status response"),
    ],
)
def test_status_returns_diagnostic_for_command_failure(tmp_path, completed, detail):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch("kimi_code_usage.providers.webbridge.subprocess.run", return_value=completed),
    ):
        status = get_webbridge_status()
    assert status.installed is True
    assert status.running is False
    assert detail in (status.detail or "")


@pytest.mark.parametrize("exc", [OSError("socket gone"), subprocess.TimeoutExpired("kimi-webbridge", 3)])
def test_status_reports_launch_error_as_detail(tmp_path, exc):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch("kimi_code_usage.providers.webbridge.subprocess.run", side_effect=exc),
    ):
        status = get_webbridge_status()
    assert status == WebBridgeStatus(True, False, False, str(exc))


def test_start_waits_for_browser_extension_after_daemon_is_ready(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    stopped = WebBridgeStatus(True, False, False)
    running = WebBridgeStatus(True, True, False)
    connected = WebBridgeStatus(True, True, True)
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("started"),
        ) as run,
        patch(
            "kimi_code_usage.providers.webbridge.get_webbridge_status",
            side_effect=[stopped, running, connected],
        ),
        patch("kimi_code_usage.providers.webbridge.time.sleep"),
    ):
        assert (
            start_webbridge(
                timeout_seconds=1,
                extension_timeout_seconds=30,
                poll_interval=0.01,
            )
            == connected
        )
    assert run.call_args.args[0] == [str(binary), "start"]
    assert run.call_args.kwargs["shell"] is False


def test_start_failure_is_exposed_as_process_local_diagnostic(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("", returncode=1, stderr="cannot bind"),
        ),
    ):
        with pytest.raises(WebBridgeLifecycleError, match="cannot bind"):
            start_webbridge()
    assert last_webbridge_start_error() == "cannot bind"


def test_start_times_out_when_daemon_never_runs(tmp_path):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    stopped = WebBridgeStatus(True, False, False)
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("started"),
        ),
        patch(
            "kimi_code_usage.providers.webbridge.get_webbridge_status",
            return_value=stopped,
        ),
        patch(
            "kimi_code_usage.providers.webbridge.time.monotonic",
            side_effect=[0.0, 0.0, 4.0],
        ),
        patch("kimi_code_usage.providers.webbridge.time.sleep"),
    ):
        with pytest.raises(WebBridgeLifecycleError, match="did not become ready"):
            start_webbridge(timeout_seconds=3)


def test_start_reports_missing_binary_as_lifecycle_error(tmp_path):
    with patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", tmp_path / "missing"):
        with pytest.raises(WebBridgeLifecycleError, match="not installed"):
            start_webbridge()
    assert last_webbridge_start_error() == "Kimi WebBridge is not installed"


@pytest.mark.parametrize("exc", [OSError("socket gone"), subprocess.TimeoutExpired("kimi-webbridge", 3)])
def test_start_propagates_process_launch_error(tmp_path, exc):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch("kimi_code_usage.providers.webbridge.subprocess.run", side_effect=exc),
    ):
        with pytest.raises(WebBridgeLifecycleError) as excinfo:
            start_webbridge()
    assert str(excinfo.value) == str(exc)
    assert last_webbridge_start_error() == str(exc)


@pytest.mark.parametrize("detail", ["browser quit", None])
def test_start_stops_when_daemon_dies_before_extension_connects(tmp_path, detail):
    binary = tmp_path / "kimi-webbridge"
    binary.touch()
    running = WebBridgeStatus(True, True, False)
    dead = WebBridgeStatus(True, False, False, detail)
    expected = detail or "Kimi WebBridge stopped before extension connected"
    with (
        patch("kimi_code_usage.providers.webbridge.WEBBRIDGE_BIN", binary),
        patch(
            "kimi_code_usage.providers.webbridge.subprocess.run",
            return_value=_completed("started"),
        ),
        patch(
            "kimi_code_usage.providers.webbridge.get_webbridge_status",
            side_effect=[running, dead],
        ),
        patch("kimi_code_usage.providers.webbridge.time.sleep"),
    ):
        with pytest.raises(WebBridgeLifecycleError, match=expected):
            start_webbridge(timeout_seconds=1, extension_timeout_seconds=30, poll_interval=0.01)
    assert last_webbridge_start_error() == expected
