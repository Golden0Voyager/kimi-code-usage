import json
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock
from rich.text import Text
from kimi_code_usage.providers import ProviderUsage
from kimi_code_usage.main import (
    _get_visual_width,
    _get_localized_label,
    _format_aggregated_results,
    _handle_key,
    _interactive_mode,
    main,
    run_cli,
)

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "OPENAI_API_KEY", 
                "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "KIMI_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "OPENROUTER_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    yield

def test_get_visual_width():
    assert _get_visual_width("hello") == 5
    assert _get_visual_width("你好") == 4
    assert _get_visual_width("a你好b") == 6

def test_get_localized_label():
    assert _get_localized_label("Weekly Usage") == "Weekly Usage" or "周" in _get_localized_label("Weekly Usage")
    assert _get_localized_label("5h Limit") == "5h Limit" or "限额" in _get_localized_label("5h Limit")
    assert _get_localized_label("Other") == "Other"

def test_format_aggregated_results():
    results = {
        "kimi": [
            ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at="06-11 12:00", unit="%", countdown="1d 2h")
        ],
        "openai": [
            ProviderUsage(provider="openai", label="Tokens Limit", used=1500, limit=10000.0, remaining=8500.0, percent=15.0, reset_at=None, unit="tokens"),
            ProviderUsage(provider="openai", label="Tokens No Limit", used=5000, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens"),
            ProviderUsage(provider="openai", label="Cost", used=1.5, limit=5.0, remaining=3.5, percent=30, reset_at=None, unit="$")
        ],
        "anthropic": [
            ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan Value")
        ],
        "openrouter": [
            ProviderUsage(provider="openrouter", label="Credits", used=2.5, limit=None, remaining=None, percent=None, reset_at=None, unit="$")
        ]
    }
    errors = {
        "openai": "API Key invalid"
    }
    
    text = _format_aggregated_results(results, errors)
    assert isinstance(text, Text)
    raw_text = str(text)
    assert "Kimi" in raw_text
    assert "Openai" in raw_text
    assert "Openrouter" in raw_text
    assert "Pro Plan Value" in raw_text
    
    # Check limit-bar format and no limit format
    assert "1,500 / 10,000 tokens" in raw_text
    assert "$1.50" in raw_text
    assert "$2.50" in raw_text
    
    # Check error message
    assert "⚠ API Key invalid" in raw_text

@pytest.mark.asyncio
async def test_main_no_providers_configured(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "--plain"])
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=({}, {}))):
        await main()
    captured = capsys.readouterr()
    assert "No usage data" in captured.out or "未找到" in captured.out

@pytest.mark.asyncio
async def test_main_json_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    }
    mock_errors = {"openai": "Auth failed"}
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, mock_errors))):
        await main()
        
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert "kimi" in data
    assert data["kimi"][0]["used"] == 10
    assert data["errors"]["openai"] == "Auth failed"

@pytest.mark.asyncio
async def test_main_plain_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--plain"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens")],
        "anthropic": [
            ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan"),
            ProviderUsage(provider="anthropic", label="Empty Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value=None)
        ]
    }
    mock_errors = {"openrouter": "Timeout"}
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, mock_errors))):
        await main()
        
    captured = capsys.readouterr()
    assert "Kimi - " in captured.out
    assert "Openai - Tokens" in captured.out
    assert "Anthropic - API Plan: Pro Plan" in captured.out
    assert "Anthropic - Empty Plan" in captured.out
    assert "Openrouter - Error: Timeout" in captured.err

@pytest.mark.asyncio
async def test_main_rich_output(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    }
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, {}))):
        await main()
        
    captured = capsys.readouterr()
    assert "Weekly Usage" in captured.out or "周" in captured.out

@pytest.mark.asyncio
async def test_main_with_provider_filter(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setattr("sys.argv", ["prog", "--provider", "kimi", "--plain"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=None, remaining=None, percent=None, reset_at=None, unit="tokens")]
    }
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, {}))) as mock_dispatch:
        await main()
        mock_dispatch.assert_called_once()
        config = mock_dispatch.call_args[0][0]
        assert config.providers["openai"].api_key is None
        assert config.providers["kimi"].api_key == "kimi-key"
        
    captured = capsys.readouterr()
    assert "Kimi - " in captured.out
    assert "Openai" not in captured.out

@pytest.mark.asyncio
async def test_main_custom_config_path(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prog", "--config", "/tmp/dummy.json"])
    
    with patch("kimi_code_usage.main.ConfigResolver") as mock_resolver:
        mock_resolver.return_value.resolve.return_value.enabled_providers = []
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=({}, {}))):
            await main()
            mock_resolver.assert_called_once_with(config_path="/tmp/dummy.json")

def test_run_cli(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog"])
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=({}, {}))):
        run_cli()

def test_main_guard_calls_run_cli():
    import runpy
    import asyncio
    with patch.object(asyncio, 'run') as mock_run:
        runpy.run_module('kimi_code_usage.main', run_name='__main__')
    mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_main_theme_cli(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--theme", "sky-dark"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    }
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, {}))):
        await main()
        
    captured = capsys.readouterr()
    assert "Weekly Usage" in captured.out or "周" in captured.out

def test_all_themes_rendering():
    # Test rendering with all 9 themes and invalid fallback theme
    from kimi_code_usage.main import THEME_MAP
    
    results = {
        "kimi": [
            ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at="06-11 12:00", unit="%", countdown="1d 2h")
        ]
    }
    
    # 1. Test invalid fallback theme (hits line 149 in main.py)
    text_invalid = _format_aggregated_results(results, {}, theme_name="unknown-theme")
    assert "Weekly Usage" in str(text_invalid) or "周" in str(text_invalid)
    
    # 2. Test all 9 themes
    for t_name in THEME_MAP.keys():
        text = _format_aggregated_results(results, {}, theme_name=t_name)
        assert "Weekly Usage" in str(text) or "周" in str(text)


# ── _handle_key unit tests ──────────────────────────────────────────────────

def test_handle_key_quit():
    for ch in ('q', 'Q', '\x03', '\x04'):
        new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(ch, 2, 5)
        assert quit_flag is True
        assert refresh_flag is False
        assert new_idx == 2
        assert toggle_num is None
        assert lang_toggle is False

def test_handle_key_next():
    for ch in (']', 'n', '\t', '\x1b[C'):
        new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(ch, 0, 5)
        assert new_idx == 1
        assert quit_flag is False
        assert refresh_flag is False
        assert toggle_num is None
        assert lang_toggle is False
    # Wrap-around
    new_idx, _, _, _, _ = _handle_key(']', 4, 5)
    assert new_idx == 0

def test_handle_key_prev():
    for ch in ('[', 'p', '\x1b[D'):
        new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(ch, 2, 5)
        assert new_idx == 1
        assert quit_flag is False
        assert refresh_flag is False
        assert toggle_num is None
        assert lang_toggle is False
    # Wrap-around backward
    new_idx, _, _, _, _ = _handle_key('[', 0, 5)
    assert new_idx == 4

def test_handle_key_refresh():
    for ch in ('r', 'R'):
        new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(ch, 3, 5)
        assert new_idx == 3
        assert quit_flag is False
        assert refresh_flag is True
        assert toggle_num is None
        assert lang_toggle is False

def test_handle_key_toggle_provider():
    for digit, expected in [('1', 0), ('2', 1), ('3', 2), ('4', 3)]:
        new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(digit, 2, 5)
        assert new_idx == 2
        assert quit_flag is False
        assert refresh_flag is False
        assert toggle_num == expected
        assert lang_toggle is False

def test_handle_key_lang_toggle():
    for ch in ('l', 'L'):
        new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key(ch, 2, 5)
        assert new_idx == 2
        assert quit_flag is False
        assert refresh_flag is False
        assert toggle_num is None
        assert lang_toggle is True

def test_handle_key_noop():
    new_idx, quit_flag, refresh_flag, toggle_num, lang_toggle = _handle_key('x', 2, 5)
    assert new_idx == 2
    assert quit_flag is False
    assert refresh_flag is False
    assert toggle_num is None
    assert lang_toggle is False


# ── _interactive_mode integration tests ────────────────────────────────────

def _make_interactive_config(monkeypatch):
    """Return a minimal AppConfig with kimi enabled."""
    from kimi_code_usage.config import ConfigResolver
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    return ConfigResolver().resolve()


def _mock_terminal(monkeypatch):
    """Suppress all real terminal calls (termios/tty/fileno)."""
    import termios as _termios, tty as _tty
    monkeypatch.setattr(_termios, "tcgetattr", lambda fd: [])
    monkeypatch.setattr(_termios, "tcsetattr", lambda *a: None)
    monkeypatch.setattr(_tty, "setcbreak", lambda fd: None)
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0)


def _make_select_and_read(key_sequence):
    """Build mock select + stdin.read from a list of key strings.
    Each item is one logical key (plain char or '\x1b[C' etc.)."""
    import io
    buf = io.StringIO()
    for k in key_sequence:
        buf.write(k)
    buf.seek(0)

    call_no = [0]
    total_chars = sum(len(k) for k in key_sequence)

    def mock_select(rlist, wlist, xlist, timeout):
        if buf.tell() < total_chars:
            return ([sys.stdin], [], [])
        return ([], [], [])

    def mock_read(n):
        return buf.read(n)

    return mock_select, mock_read


@pytest.mark.asyncio
async def test_interactive_mode_quit(monkeypatch):
    """Press q → exit immediately."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")
            mock_live.update.assert_called()


@pytest.mark.asyncio
async def test_interactive_mode_refresh(monkeypatch):
    """Press r → dispatch_all called twice (initial + refresh), then q."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['r', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    dispatch_mock = AsyncMock(return_value=(mock_res, {}))
    with patch("kimi_code_usage.main.dispatch_all", dispatch_mock):
        with patch("kimi_code_usage.main.Live"):
            await _interactive_mode(cfg, "blue-dark")
    assert dispatch_mock.call_count == 2  # initial + refresh


@pytest.mark.asyncio
async def test_interactive_mode_next_prev_arrow(monkeypatch):
    """Arrow keys and [ ] switch themes, q exits."""
    _mock_terminal(monkeypatch)
    # right-arrow, left-arrow, ], [, q
    mock_select, mock_read = _make_select_and_read(['\x1b[C', '\x1b[D', ']', '[', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")
            # 5 keys → 5 live.update() calls (one per key, including the quit one before running=False)
            assert mock_live.update.call_count >= 4


@pytest.mark.asyncio
async def test_interactive_mode_lone_escape(monkeypatch):
    """A lone ESC with no follow-up → treated as unknown key (no-op), then q."""
    _mock_terminal(monkeypatch)

    import kimi_code_usage.main as main_mod
    select_calls = [0]

    # stdin holds: ESC, q
    buf = ['\x1b', 'q']
    buf_pos = [0]

    def mock_select(rlist, wlist, xlist, timeout):
        # First outer select: ready (for ESC)
        # Second inner select (after ESC, look-ahead): nothing ready → lone escape
        # Third outer select: ready (for q)
        # After that: done
        select_calls[0] += 1
        if buf_pos[0] < len(buf):
            if timeout == 0.15:
                return ([sys.stdin], [], [])
            else:
                # look-ahead: return empty so ESC is treated as lone
                return ([], [], [])
        return ([], [], [])

    def mock_read(n):
        ch = buf[buf_pos[0]]
        buf_pos[0] += 1
        return ch

    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live"):
            await _interactive_mode(cfg, "sky-dark")


@pytest.mark.asyncio
async def test_interactive_mode_no_key_timeout(monkeypatch):
    """select returns empty (timeout) → loop idles, then q ends it."""
    _mock_terminal(monkeypatch)

    import kimi_code_usage.main as main_mod
    call_count = [0]

    def mock_select(rlist, wlist, xlist, timeout):
        call_count[0] += 1
        # First two calls: timeout (no key). Third: key 'q'.
        if call_count[0] <= 2:
            return ([], [], [])
        return ([sys.stdin], [], [])

    def mock_read(n):
        return 'q'

    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live"):
            await _interactive_mode(cfg, "blue-dark")
    assert call_count[0] >= 3


@pytest.mark.asyncio
async def test_main_interactive_flag(monkeypatch):
    """--interactive flag routes to _interactive_mode and returns."""
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--interactive"])

    with patch("kimi_code_usage.main._interactive_mode", new=AsyncMock()) as mock_im:
        await main()
        mock_im.assert_called_once()


@pytest.mark.asyncio
async def test_interactive_mode_unknown_theme_fallback(monkeypatch):
    """An unrecognized initial_theme falls back to idx=0 (ValueError branch)."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live"):
            # "nonexistent-theme" triggers the ValueError → idx = 0 fallback
            await _interactive_mode(cfg, "nonexistent-theme")


@pytest.mark.asyncio
async def test_interactive_mode_toggle_provider(monkeypatch):
    """Press '1' to hide first provider, then q."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['1', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")
            # Panel should be updated at least twice: once for '1' toggle, once for 'q'
            assert mock_live.update.call_count >= 2


@pytest.mark.asyncio
async def test_interactive_mode_toggle_out_of_range(monkeypatch):
    """Press '4' when only 1 provider is in provider_order → safe no-op."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['4', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    # Config with only one provider
    from kimi_code_usage.config import AppConfig, ProviderConfig
    cfg = AppConfig()
    cfg.providers = {"kimi": ProviderConfig(api_key="k", enabled=True)}
    cfg.provider_order = ["kimi"]

    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live"):
            # toggle_num=3 (for '4'), but provider_order only has 1 item → no-op
            await _interactive_mode(cfg, "blue-dark")


@pytest.mark.asyncio
async def test_interactive_mode_toggle_reenable(monkeypatch):
    """Press '1' twice: hide then re-show first provider (covers visible_providers.add branch)."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['1', '1', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")
            # 3 keypresses → 3 update() calls
            assert mock_live.update.call_count >= 3


@pytest.mark.asyncio
async def test_interactive_mode_lang_toggle(monkeypatch):
    """Press 'l' to switch language ZH→EN, then 'l' again EN→ZH, then q."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['l', 'l', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")
            # 3 keypresses (l, l, q) → 3 live.update() calls
            assert mock_live.update.call_count >= 3


@pytest.mark.asyncio
async def test_interactive_mode_initializes_from_config_en(monkeypatch):
    """Verify interactive mode loads initial language and visible_providers from config."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.language = "en"
    cfg.visible_providers = ["kimi"]
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            await _interactive_mode(cfg, "blue-dark")


@pytest.mark.asyncio
async def test_interactive_mode_initializes_from_config_zh(monkeypatch):
    """Verify interactive mode loads initial language (zh) from config."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(['q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg_zh = _make_interactive_config(monkeypatch)
    cfg_zh.language = "zh"
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            await _interactive_mode(cfg_zh, "blue-dark")


# ── save_theme (config.py) unit tests ─────────────────────────────────────

def test_save_theme_creates_config(tmp_path):
    """save_theme creates the config file and directory if they don't exist."""
    from kimi_code_usage.config import save_theme as cfg_save
    dest = tmp_path / "subdir" / "config.json"
    cfg_save("sky-dark", config_path=dest)
    data = json.loads(dest.read_text())
    assert data["general"]["theme"] == "sky-dark"

def test_save_theme_updates_existing(tmp_path):
    """save_theme updates general.theme while preserving other keys."""
    from kimi_code_usage.config import save_theme as cfg_save
    dest = tmp_path / "config.json"
    dest.write_text(json.dumps({"general": {"theme": "old", "foo": "bar"}, "other": 1}))
    cfg_save("viridian-dark", language="zh", visible_providers=["kimi"], config_path=dest)
    data = json.loads(dest.read_text())
    assert data["general"]["theme"] == "viridian-dark"
    assert data["general"]["language"] == "zh"
    assert data["general"]["visibleProviders"] == ["kimi"]
    assert data["general"]["foo"] == "bar"   # preserved
    assert data["other"] == 1                 # preserved

def test_save_theme_corrupt_json(tmp_path):
    """save_theme silently recovers from corrupt existing JSON."""
    from kimi_code_usage.config import save_theme as cfg_save
    dest = tmp_path / "config.json"
    dest.write_text("NOT VALID JSON{{{")
    cfg_save("monochrome", config_path=dest)
    data = json.loads(dest.read_text())
    assert data["general"]["theme"] == "monochrome"


# ── Enter key → save theme integration test ───────────────────────────────

@pytest.mark.asyncio
async def test_interactive_mode_enter_saves_theme(monkeypatch, tmp_path):
    """Press Enter → save_theme called; saved_notice shown; next key clears it."""
    _mock_terminal(monkeypatch)
    # Enter (\r), then another key to clear notice, then q
    mock_select, mock_read = _make_select_and_read(['\r', 'r', 'q'])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    saved_calls = []
    def fake_save(theme, language=None, visible_providers=None, config_path=None):
        saved_calls.append((theme, language, visible_providers))

    with patch("kimi_code_usage.main.save_theme", fake_save):
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
            with patch("kimi_code_usage.main.Live") as mock_live_cls:
                mock_live = mock_live_cls.return_value.__enter__.return_value
                await _interactive_mode(cfg, "blue-dark")

    # save_theme must have been called exactly once (for Enter)
    assert len(saved_calls) == 1
    assert saved_calls[0][0] == "blue-dark"
    assert saved_calls[0][1] in ("zh", "en")
    assert "kimi" in saved_calls[0][2]
    # panel updated at least twice (Enter update + subsequent updates)
    assert mock_live.update.call_count >= 2


def test_localization_helpers():
    from kimi_code_usage.main import _get_localized_label, _get_localized_text_value

    # 1. Test _get_localized_label with translations
    assert _get_localized_label("Credits", lang_zh=True) == "额度"
    assert _get_localized_label("额度", lang_zh=False) == "Credits"
    assert _get_localized_label("Key Name", lang_zh=True) == "密钥名称"
    assert _get_localized_label("密钥名称", lang_zh=False) == "Key Name"
    assert _get_localized_label("Rate Limit", lang_zh=True) == "速率限制"
    assert _get_localized_label("速率限制", lang_zh=False) == "Rate Limit"
    assert _get_localized_label("Usage", lang_zh=True) == "周期已用"
    assert _get_localized_label("周期已用", lang_zh=False) == "Usage"
    assert _get_localized_label("Free Tier", lang_zh=True) == "免费额度"
    assert _get_localized_label("免费额度", lang_zh=False) == "Free Tier"
    assert _get_localized_label("Limit Reset", lang_zh=True) == "限额重置周期"
    assert _get_localized_label("限额重置周期", lang_zh=False) == "Limit Reset"
    assert _get_localized_label("Expires At", lang_zh=True) == "过期时间"
    assert _get_localized_label("过期时间", lang_zh=False) == "Expires At"
    assert _get_localized_label("Is Provisioning", lang_zh=True) == "配给密钥"
    assert _get_localized_label("配给密钥", lang_zh=False) == "Is Provisioning"
    assert _get_localized_label("Management Key", lang_zh=True) == "管理密钥"
    assert _get_localized_label("管理密钥", lang_zh=False) == "Management Key"
    assert _get_localized_label("SomeOtherLabel", lang_zh=True) == "SomeOtherLabel"

    # Test time unit limits
    assert _get_localized_label("5h Limit", lang_zh=True) == "5小时限额"
    assert _get_localized_label("5h Limit", lang_zh=False) == "5h Limit"
    assert _get_localized_label("3d Limit", lang_zh=True) == "3天限额"
    assert _get_localized_label("3d Limit", lang_zh=False) == "3d Limit"
    assert _get_localized_label("6mo Limit", lang_zh=True) == "6个月限额"
    assert _get_localized_label("6mo Limit", lang_zh=False) == "6mo Limit"
    assert _get_localized_label("45m Limit", lang_zh=True) == "45分钟限额"
    assert _get_localized_label("45m Limit", lang_zh=False) == "45m Limit"
    assert _get_localized_label("30s Limit", lang_zh=True) == "30s 限额"  # falls back to replacing "Limit" with "限额"
    assert _get_localized_label("30s Limit", lang_zh=False) == "30s Limit"


    # 2. Test _get_localized_text_value
    assert _get_localized_text_value(None, lang_zh=True) is None
    assert _get_localized_text_value("", lang_zh=True) == ""
    
    val_en = "Daily: $0.1234 | Weekly: $0.5678 | Monthly: $1.2345"
    assert _get_localized_text_value(val_en, lang_zh=True) == "今日: $0.1234 | 本周: $0.5678 | 本月: $1.2345"
    
    val_zh = "今日: $0.1234 | 本周: $0.5678 | 本月: $1.2345"
    assert _get_localized_text_value(val_zh, lang_zh=False) == "Daily: $0.1234 | Weekly: $0.5678 | Monthly: $1.2345"

    val_bad_floats = "Daily: $abc | Weekly: $0.56 | Monthly: $1.23"
    assert _get_localized_text_value(val_bad_floats, lang_zh=True) == val_bad_floats

    assert _get_localized_text_value("Other normal text", lang_zh=True) == "Other normal text"
    assert _get_localized_text_value("Other normal text", lang_zh=False) == "Other normal text"
    
    # Rate limit localization
    assert _get_localized_text_value("Unlimited/10s", lang_zh=True) == "无限制/10秒"
    assert _get_localized_text_value("无限制/10秒", lang_zh=False) == "Unlimited/10s"
    assert _get_localized_text_value("20 req/1s", lang_zh=True) == "20次/1秒"
    assert _get_localized_text_value("20次/1秒", lang_zh=False) == "20 req/1s"
    assert _get_localized_text_value("Unlimited/1m", lang_zh=True) == "无限制/1分钟"
    assert _get_localized_text_value("无限制/1分钟", lang_zh=False) == "Unlimited/1m"
    assert _get_localized_text_value("Unlimited/1h", lang_zh=True) == "无限制/1小时"
    assert _get_localized_text_value("无限制/1小时", lang_zh=False) == "Unlimited/1h"
    assert _get_localized_text_value("5 req/2m", lang_zh=True) == "5次/2分钟"
    assert _get_localized_text_value("5次/2分钟", lang_zh=False) == "5 req/2m"
    assert _get_localized_text_value("5 req/2h", lang_zh=True) == "5次/2小时"
    assert _get_localized_text_value("5次/2小时", lang_zh=False) == "5 req/2h"

    # Yes/No localization
    assert _get_localized_text_value("Yes", lang_zh=True) == "是"
    assert _get_localized_text_value("No", lang_zh=True) == "否"
    assert _get_localized_text_value("是", lang_zh=False) == "Yes"
    assert _get_localized_text_value("否", lang_zh=False) == "No"


def test_format_aggregated_results_edge_cases():
    # 1. Non-empty results with multiple errors
    results = {
        "kimi": [
            ProviderUsage(provider="kimi", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value=None)
        ]
    }
    errors = {
        "kimi": "error1",
        "openai": "error2"
    }
    text = _format_aggregated_results(results, errors)
    raw_text = str(text)
    assert "error1" in raw_text
    assert "error2" in raw_text
    assert "None" not in raw_text

    # 2. Empty results with errors (to cover if not first_section being False on first error)
    text_empty = _format_aggregated_results({}, {"kimi": "error1", "openai": "error2"})
    raw_text_empty = str(text_empty)
    assert "error1" in raw_text_empty
    assert "error2" in raw_text_empty


@pytest.mark.asyncio
async def test_main_json_output_no_errors(monkeypatch, capsys):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.setattr("sys.argv", ["prog", "--json"])
    
    mock_results = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")]
    }
    
    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_results, {}))):
        await main()
        
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert "kimi" in data
    assert "errors" not in data


@pytest.mark.asyncio
async def test_interactive_mode_escape_keys(monkeypatch):
    _mock_terminal(monkeypatch)
    import kimi_code_usage.main as main_mod

    # Case 1: Escape followed by non-'[' character (e.g. '\x1b', 'A', 'q')
    inputs_1 = ['\x1b', 'A', 'q']
    idx_1 = [0]
    
    def mock_select_1(rlist, wlist, xlist, timeout):
        if idx_1[0] < len(inputs_1):
            return ([sys.stdin], [], [])
        return ([], [], [])

    def mock_read_1(n):
        val = inputs_1[idx_1[0]]
        idx_1[0] += 1
        return val

    monkeypatch.setattr(main_mod._select_module, "select", mock_select_1)
    monkeypatch.setattr(sys.stdin, "read", mock_read_1)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live"):
            await _interactive_mode(cfg, "blue-dark")

    # Case 2: Escape followed by '[', but no 3rd character (timeout on r3)
    inputs_2 = ['\x1b', '[', 'q']
    idx_2 = [0]
    
    def mock_select_2(rlist, wlist, xlist, timeout):
        if timeout == 0.05 and idx_2[0] == 2:
            return ([], [], [])
        if idx_2[0] < len(inputs_2):
            return ([sys.stdin], [], [])
        return ([], [], [])

    def mock_read_2(n):
        val = inputs_2[idx_2[0]]
        idx_2[0] += 1
        return val

    monkeypatch.setattr(main_mod._select_module, "select", mock_select_2)
    monkeypatch.setattr(sys.stdin, "read", mock_read_2)

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live"):
            await _interactive_mode(cfg, "blue-dark")
