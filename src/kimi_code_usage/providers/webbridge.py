from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

WEBBRIDGE_BIN = Path.home() / ".kimi-webbridge" / "bin" / "kimi-webbridge"
_LAST_START_ERROR: str | None = None


class WebBridgeLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebBridgeStatus:
    installed: bool
    running: bool
    extension_connected: bool
    detail: str | None = None


def get_webbridge_status() -> WebBridgeStatus:
    if not WEBBRIDGE_BIN.exists():
        return WebBridgeStatus(False, False, False)
    try:
        result = subprocess.run(
            [str(WEBBRIDGE_BIN), "status"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return WebBridgeStatus(True, False, False, str(exc))
    if result.returncode != 0:
        return WebBridgeStatus(
            True,
            False,
            False,
            result.stderr.strip() or f"status exited {result.returncode}",
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return WebBridgeStatus(True, False, False, "invalid status response")
    if not isinstance(payload, dict):
        return WebBridgeStatus(True, False, False, "invalid status response")
    return WebBridgeStatus(
        installed=True,
        running=bool(payload.get("running")),
        extension_connected=bool(payload.get("extension_connected")),
    )


def last_webbridge_start_error() -> str | None:
    return _LAST_START_ERROR


def _set_start_error(message: str | None) -> None:
    global _LAST_START_ERROR
    _LAST_START_ERROR = message


def start_webbridge(
    *,
    timeout_seconds: float = 3.0,
    extension_timeout_seconds: float = 30.0,
    poll_interval: float = 0.5,
) -> WebBridgeStatus:
    if not WEBBRIDGE_BIN.exists():
        message = "Kimi WebBridge is not installed"
        _set_start_error(message)
        raise WebBridgeLifecycleError(message)
    _set_start_error(None)
    try:
        result = subprocess.run(
            [str(WEBBRIDGE_BIN), "start"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _set_start_error(str(exc))
        raise WebBridgeLifecycleError(str(exc)) from exc
    if result.returncode != 0:
        message = result.stderr.strip() or f"start exited {result.returncode}"
        _set_start_error(message)
        raise WebBridgeLifecycleError(message)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = get_webbridge_status()
        if status.running:
            break
        time.sleep(poll_interval)
    else:
        message = "Kimi WebBridge did not become ready before timeout"
        _set_start_error(message)
        raise WebBridgeLifecycleError(message)

    extension_deadline = time.monotonic() + extension_timeout_seconds
    while not status.extension_connected and time.monotonic() < extension_deadline:
        time.sleep(poll_interval)
        status = get_webbridge_status()
        if not status.running:
            message = status.detail or "Kimi WebBridge stopped before extension connected"
            _set_start_error(message)
            raise WebBridgeLifecycleError(message)
    return status
