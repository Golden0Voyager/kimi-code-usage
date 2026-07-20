import json
import sys
from unittest.mock import AsyncMock, patch

import pytest
from rich.text import Text

from kimi_code_usage.main import (
    THEME_MAP,
    _format_aggregated_results,
    _get_localized_label,
    _get_visual_width,
    _handle_key,
    _interactive_mode,
    _render_activity_totals,
    _render_daily_chart,
    _render_top_models,
    main,
    run_cli,
)
from kimi_code_usage.providers import ActivityTotals, DailyUsage, ModelUsage, ProviderUsage


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
    assert "OpenAI API" in raw_text
    assert "OpenRouter" in raw_text
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
    import asyncio
    import runpy
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
    for t_name in THEME_MAP:
        text = _format_aggregated_results(results, {}, theme_name=t_name)
        assert "Weekly Usage" in str(text) or "周" in str(text)


# ── _handle_key unit tests ──────────────────────────────────────────────────

@pytest.mark.parametrize("ch,idx,n,expected", [
    ('q', 2, 5, (2, True, False, None, False, False, False)),
    ('Q', 2, 5, (2, True, False, None, False, False, False)),
    ('\x03', 2, 5, (2, True, False, None, False, False, False)),
    ('\x04', 2, 5, (2, True, False, None, False, False, False)),
    (']', 0, 5, (1, False, False, None, False, False, False)),
    ('n', 0, 5, (1, False, False, None, False, False, False)),
    ('\t', 0, 5, (1, False, False, None, False, False, False)),
    ('\x1b[C', 0, 5, (1, False, False, None, False, False, False)),
    (']', 4, 5, (0, False, False, None, False, False, False)),  # wrap forward
    ('[', 2, 5, (1, False, False, None, False, False, False)),
    ('p', 2, 5, (1, False, False, None, False, False, False)),
    ('\x1b[D', 2, 5, (1, False, False, None, False, False, False)),
    ('[', 0, 5, (4, False, False, None, False, False, False)),  # wrap backward
    ('r', 3, 5, (3, False, True, None, False, False, False)),
    ('R', 3, 5, (3, False, True, None, False, False, False)),
    ('1', 2, 5, (2, False, False, 0, False, False, False)),
    ('2', 2, 5, (2, False, False, 1, False, False, False)),
    ('3', 2, 5, (2, False, False, 2, False, False, False)),
    ('4', 2, 5, (2, False, False, 3, False, False, False)),
    ('l', 2, 5, (2, False, False, None, True, False, False)),
    ('L', 2, 5, (2, False, False, None, True, False, False)),
    ('m', 2, 5, (2, False, False, None, False, True, False)),
    ('M', 2, 5, (2, False, False, None, False, True, False)),
    ('d', 2, 5, (2, False, False, None, False, False, True)),
    ('D', 2, 5, (2, False, False, None, False, False, True)),
    ('x', 2, 5, (2, False, False, None, False, False, False)),
])
def test_handle_key(ch, idx, n, expected):
    assert _handle_key(ch, idx, n) == expected


# ── _interactive_mode integration tests ────────────────────────────────────

def _make_interactive_config(monkeypatch):
    """Return a minimal AppConfig with kimi enabled."""
    from kimi_code_usage.config import ConfigResolver
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    return ConfigResolver().resolve()


def _mock_terminal(monkeypatch):
    """Suppress all real terminal calls (termios/tty/fileno)."""
    import termios as _termios
    import tty as _tty
    monkeypatch.setattr(_termios, "tcgetattr", lambda fd: [])
    monkeypatch.setattr(_termios, "tcsetattr", lambda *a: None)
    monkeypatch.setattr(_tty, "setcbreak", lambda fd: None)
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0)
    # Tall terminal so the interactive panel fits without scroll truncation,
    # keeping content assertions stable (fit/scroll logic is unit-tested separately).
    monkeypatch.setenv("LINES", "200")


def _make_select_and_read(key_sequence):
    """Build mock select + stdin.read from a list of key strings.
    Each item is one logical key (plain char or '\x1b[C' etc.)."""
    import io
    buf = io.StringIO()
    for k in key_sequence:
        buf.write(k)
    buf.seek(0)

    total_chars = sum(len(k) for k in key_sequence)

    def mock_select(rlist, wlist, xlist, timeout):
        if buf.tell() < total_chars:
            return ([sys.stdin], [], [])
        return ([], [], [])

    def mock_read(n):
        return buf.read(n)

    return mock_select, mock_read


def _run_interactive_mode(monkeypatch, keys, theme="blue-dark", cfg=None, dispatch_call_count=None, live_update_min=None):
    """Run _interactive_mode with a mocked terminal and stdin key sequence."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(keys)
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = cfg or _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    dispatch_mock = AsyncMock(return_value=(mock_res, {}))
    with patch("kimi_code_usage.main.dispatch_all", dispatch_mock):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            import asyncio
            asyncio.run(_interactive_mode(cfg, theme))
            if live_update_min is not None:
                assert mock_live.update.call_count >= live_update_min
    if dispatch_call_count is not None:
        assert dispatch_mock.call_count == dispatch_call_count
    return dispatch_mock


def _cfg_one_provider(m):
    from kimi_code_usage.config import AppConfig, ProviderConfig
    cfg = AppConfig()
    cfg.providers = {"kimi": ProviderConfig(api_key="k", enabled=True)}
    cfg.provider_order = ["kimi"]
    return cfg


def _panel_plain(panel):
    parts = []
    for item in getattr(panel.renderable, "renderables", []):
        if hasattr(item, "plain"):
            parts.append(item.plain)
        else:
            parts.append(str(item))
    return "\n".join(parts)


@pytest.mark.parametrize("keys,theme,live_update_min,dispatch_call_count,cfg_maker", [
    (["q"], "blue-dark", 1, 1, None),
    (["r", "q"], "blue-dark", 2, 2, None),
    (["\x1b[C", "\x1b[D", "]", "[", "q"], "blue-dark", 4, 1, None),
    (["1", "q"], "blue-dark", 2, 1, None),
    (["4", "q"], "blue-dark", 2, 1, _cfg_one_provider),
    (["1", "1", "q"], "blue-dark", 3, 1, None),
    (["l", "l", "q"], "blue-dark", 3, 1, None),
    (["m", "d", "q"], "blue-dark", 3, 1, None),
    (["\x1b[B", "\x1b[A", "\x1b[6~", "\x1b[5~", "q"], "blue-dark", 4, 1, None),
    (["q"], "nonexistent-theme", 1, 1, None),
])
def test_interactive_mode_common_keys(monkeypatch, keys, theme, live_update_min, dispatch_call_count, cfg_maker):
    """Common interactive key sequences."""
    cfg = cfg_maker(monkeypatch) if cfg_maker else _make_interactive_config(monkeypatch)
    _run_interactive_mode(monkeypatch, keys, theme=theme, cfg=cfg, live_update_min=live_update_min, dispatch_call_count=dispatch_call_count)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_interactive_mode_initializes_from_config(monkeypatch, language):
    """Verify interactive mode loads initial language from config."""
    cfg = _make_interactive_config(monkeypatch)
    cfg.language = language
    _run_interactive_mode(monkeypatch, ["q"], cfg=cfg, live_update_min=1, dispatch_call_count=1)


def test_render_config_guide_includes_supported_provider_setup():
    from kimi_code_usage.config import AppConfig, ProviderConfig
    from kimi_code_usage.main import _render_config_guide

    cfg = AppConfig()
    cfg.providers = {
        "kimi": ProviderConfig(api_key="sk-kimi-1234567890", base_url="https://api.kimi.com/coding/v1"),
        "openai": ProviderConfig(api_key="sk-openai-abcdef1234", base_url="https://api.openai.com"),
        "anthropic": ProviderConfig(api_key=None, base_url="https://api.anthropic.com"),
        "openrouter": ProviderConfig(api_key="sk-or-v1-abcdef1234", base_url="https://openrouter.ai/api", management_key="or-mgmt-1234"),
    }
    cfg.provider_order = ["kimi", "openai", "anthropic", "openrouter"]

    text = _render_config_guide(cfg, lang_zh=False, config_path="/tmp/kimi-usage/config.json")
    raw = text.plain

    assert "/tmp/kimi-usage/config.json" in raw
    assert "KIMI_API_KEY" in raw
    assert "OPENAI_API_KEY" in raw
    assert "ANTHROPIC_API_KEY" in raw
    assert "OPENROUTER_API_KEY" in raw
    assert "OPENROUTER_ADMIN_KEY" in raw
    assert "OPENROUTER_MANAGEMENT_KEY" in raw
    assert "https://api.kimi.com/coding/v1" in raw
    assert "https://openrouter.ai/api" in raw
    assert "https://api.moonshot.cn/v1" in raw
    assert "sk-kimi" in raw
    assert "sk-kimi-1234567890" not in raw
    assert "or-mgmt-1234" not in raw
    assert "missing" in raw


@pytest.mark.asyncio
async def test_interactive_mode_help_and_config_keys(monkeypatch):
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["h", "c", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    mock_res = {"kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")]}

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    assert "Interactive Help" in rendered
    assert "Configuration Guide" in rendered
    assert "OPENAI_API_KEY" in rendered
    assert "ANTHROPIC_API_KEY" in rendered
    assert "OPENROUTER_API_KEY" in rendered


@pytest.mark.asyncio
async def test_interactive_mode_top_bar_shows_only_visible_providers(monkeypatch):
    """Top bar omits hidden providers and renumbers visible ones."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]
    cfg.visible_providers = ["kimi", "openai"]
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=1000, remaining=900, percent=10, reset_at=None, unit="tokens")],
    }

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    assert "[1]Kimi" in rendered
    assert "[2]ChatGPT+" in rendered or "[2]OpenAI API" in rendered
    assert "[3]" not in rendered
    assert "[4]" not in rendered
    assert "[5]" not in rendered
    assert "[6]" not in rendered


@pytest.mark.asyncio
async def test_interactive_mode_number_key_uses_visible_index(monkeypatch):
    """In usage view, number keys map to visible-only provider indices."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["2", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]
    cfg.visible_providers = ["kimi", "anthropic"]
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "anthropic": [ProviderUsage(provider="anthropic", label="Usage", used=10, limit=100, remaining=90, percent=10, reset_at=None, unit="%")],
    }

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    # Initial render shows [1]Kimi [2]Anthropic; pressing "2" toggles anthropic off
    # because it is the second *visible* provider, not openai (full-list index 1).
    final_render = _panel_plain(mock_live.update.call_args_list[-1].args[0])
    assert "[1]Kimi" in final_render
    assert "[2]" not in final_render


@pytest.mark.asyncio
async def test_interactive_mode_usage_number_key_targets_visible_order(monkeypatch):
    """Pressing [2] in usage view hides the second visible provider, not provider_order[1]."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["2", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic"]
    cfg.visible_providers = ["kimi", "anthropic"]  # openai is hidden
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "anthropic": [ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan")],
    }

    saved_calls = []
    def fake_save(theme, language=None, visible_providers=None, or_metric=None, days_window=None, config_path=None):
        saved_calls.append((theme, language, visible_providers, or_metric, days_window))

    with patch("kimi_code_usage.main.save_theme", fake_save):
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
            with patch("kimi_code_usage.main.Live") as mock_live_cls:
                mock_live = mock_live_cls.return_value.__enter__.return_value
                await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    # anthropic was at [2] in the visible top bar; pressing 2 should hide it
    assert "[2]Anthropic" not in rendered
    assert "[1]Kimi" in rendered


@pytest.mark.asyncio
async def test_interactive_mode_settings_number_key_toggles_full_list(monkeypatch):
    """In settings view, [2] toggles provider_order[1] even if it is not currently visible."""
    _mock_terminal(monkeypatch)
    mock_select, mock_read = _make_select_and_read(["s", "2", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic"]
    cfg.visible_providers = ["kimi", "anthropic"]  # openai starts hidden
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "anthropic": [ProviderUsage(provider="anthropic", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Pro Plan")],
    }

    saved_calls = []
    def fake_save(theme, language=None, visible_providers=None, or_metric=None, days_window=None, config_path=None):
        saved_calls.append((theme, language, visible_providers, or_metric, days_window))

    with patch("kimi_code_usage.main.save_theme", fake_save):
        with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
            with patch("kimi_code_usage.main.Live") as mock_live_cls:
                mock_live = mock_live_cls.return_value.__enter__.return_value
                await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    # After pressing 2 in settings, openai becomes visible
    assert "● [2] OpenAI API" in rendered or "● [2] OpenAI" in rendered


@pytest.mark.asyncio
async def test_interactive_mode_footer_hints_reflect_visible_count(monkeypatch):
    """Footer number range matches visible count in usage view and full count in settings view."""
    _mock_terminal(monkeypatch)
    # Refresh first to force a usage-view update (the initial panel is rendered by
    # Live on entry, not via update()), then switch to settings and quit.
    mock_select, mock_read = _make_select_and_read(["r", "s", "q"])
    import kimi_code_usage.main as main_mod
    monkeypatch.setattr(main_mod._select_module, "select", mock_select)
    monkeypatch.setattr(sys.stdin, "read", mock_read)

    cfg = _make_interactive_config(monkeypatch)
    cfg.provider_order = ["kimi", "openai", "anthropic", "openrouter", "codex", "claude"]
    cfg.visible_providers = ["kimi", "openai"]
    mock_res = {
        "kimi": [ProviderUsage(provider="kimi", label="Weekly Usage", used=5, limit=100, remaining=95, percent=5, reset_at=None, unit="%")],
        "openai": [ProviderUsage(provider="openai", label="Tokens", used=100, limit=1000, remaining=900, percent=10, reset_at=None, unit="tokens")],
    }

    with patch("kimi_code_usage.main.dispatch_all", AsyncMock(return_value=(mock_res, {}))):
        with patch("kimi_code_usage.main.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value.__enter__.return_value
            await _interactive_mode(cfg, "blue-dark")

    rendered = "\n".join(_panel_plain(call.args[0]) for call in mock_live.update.call_args_list)
    # Usage view after 'r' should show [1-2]
    # Settings view after 's' should show [1-6]
    # Because the test renders both views, assert both ranges appear at some point.
    assert "[1-2]" in rendered
    assert "[1-6]" in rendered


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
    def fake_save(theme, language=None, visible_providers=None, or_metric=None, days_window=None, config_path=None):
        saved_calls.append((theme, language, visible_providers, or_metric, days_window))

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

    # 3. Test "Not configured" error in Chinese and long error message width adjustment
    results_edge = {
        "kimi": [
            ProviderUsage(provider="kimi", label="API Plan", used=0, limit=None, remaining=None, percent=None, reset_at=None, unit="text", text_value="Short")
        ]
    }
    errors_edge = {
        "openai": "Not configured",
        "anthropic": "This is an extremely long error message that exceeds the maximum visual width of any successful panel rows"
    }
    text_zh = _format_aggregated_results(results_edge, errors_edge, lang_zh=True)
    raw_text_zh = str(text_zh)
    assert "未配置" in raw_text_zh
    assert "This is an extremely long error message" in raw_text_zh



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


def test_render_activity_totals():
    totals = ActivityTotals(
        spend=4.3,
        requests=45,
        prompt_tokens=4500,
        completion_tokens=2000,
        reasoning_tokens=300,
    )
    text = _render_activity_totals(totals, lang_zh=False, theme=THEME_MAP["blue-dark"])
    raw = str(text)
    assert "Req: 45" in raw
    assert "In: 4.5K" in raw
    assert "Out: 2.0K" in raw
    assert "+ 300 reason" in raw
    assert "$4.30" in raw


def test_render_daily_chart_variants():
    from kimi_code_usage.main import (
        _format_tokens,
        _next_days_window,
        _next_or_metric,
        _parse_days_window,
        _parse_or_metric,
        _render_top_models,
        short_date,
        truncate,
    )

    # Helper edge cases
    assert _format_tokens(2_500_000) == "2.5M"
    assert _parse_days_window("bad") == 30
    assert _parse_days_window(999) == 30
    assert _next_days_window(999) == 30
    assert _next_days_window(7) == 14
    assert _parse_or_metric("invalid") == "requests"
    assert _next_or_metric("invalid") == "requests"
    assert _next_or_metric("spend") == "requests"
    assert short_date("06-12") == "06-12"
    # Trim branch: 90-day window exceeds max_chart_width, so only recent days are shown
    from datetime import datetime, timedelta
    base = datetime(2026, 3, 16)
    wide_daily = [
        DailyUsage(date=(base + timedelta(days=i)).strftime("%Y-%m-%d"), models=[ModelUsage(model="m1", requests=1)], total=0.01)
        for i in range(90)
    ]
    text_wide = _render_daily_chart(wide_daily, lang_zh=False, theme=THEME_MAP["blue-dark"], metric="requests", days_window=90)
    raw_wide = str(text_wide)
    assert "Daily Requests" in raw_wide
    # Trimmed to the most recent 70 days, so the earliest visible label is 04-05
    assert "04-05" in raw_wide

    assert truncate("short", 10) == "short"
    assert truncate("this is a very long string", 10) == "this is..."
    assert _render_top_models([], lang_zh=False, theme=THEME_MAP["blue-dark"]).plain == ""

    # Empty chart returns empty Text
    assert str(_render_daily_chart([], lang_zh=False, theme=THEME_MAP["blue-dark"])) == ""

    # Duplicate dates are merged
    daily = [
        DailyUsage(date="2026-06-12", models=[ModelUsage(model="m1", requests=5, spend=1.5)], total=1.5),
        DailyUsage(date="2026-06-12", models=[ModelUsage(model="m2", requests=7, spend=2.0)], total=2.0),
    ]
    text = _render_daily_chart(daily, lang_zh=False, theme=THEME_MAP["blue-dark"], metric="spend", days_window=7)
    raw = str(text)
    assert "Daily Spend" in raw
    assert "$3.50" in raw

    # Tokens metric and short date fallback
    text_tokens = _render_daily_chart(
        [DailyUsage(date="2026-06-12", models=[ModelUsage(model="no-slash", requests=1, prompt_tokens=1000, completion_tokens=500)], total=0)],
        lang_zh=False,
        theme=THEME_MAP["blue-dark"],
        metric="tokens",
        days_window=7,
    )
    raw_tokens = str(text_tokens)
    assert "Daily Tokens" in raw_tokens
    assert "no-slash" in raw_tokens

    # Others segment: a model outside the top models bucket
    lots_of_models = [
        DailyUsage(
            date="2026-06-12",
            models=[
                ModelUsage(model="m1", requests=100),
                ModelUsage(model="m2", requests=90),
                ModelUsage(model="m3", requests=80),
                ModelUsage(model="m4", requests=70),
                ModelUsage(model="m5", requests=60),
                ModelUsage(model="m6", requests=50),
                ModelUsage(model="other", requests=30),
            ],
        ),
    ]
    text_others = _render_daily_chart(lots_of_models, lang_zh=False, theme=THEME_MAP["blue-dark"], metric="requests", days_window=7)
    assert "Daily Requests" in str(text_others)




@pytest.mark.parametrize("metric,expected", [
    ("spend", "$"),
    ("requests", "1,000"),
    ("tokens", "1.0M"),
])
def test_render_top_models_metrics(metric, expected):
    models = [
        ModelUsage(
            model="anthropic/claude-opus-4",
            spend=3.5,
            requests=1000,
            prompt_tokens=1_000_000,
            completion_tokens=500,
        ),
    ]
    text = _render_top_models(models, lang_zh=False, theme=THEME_MAP["blue-dark"], metric=metric)
    raw = str(text)
    assert "Top Models" in raw
    assert "claude-opus-4" in raw
    assert expected in raw


def test_render_top_models_long_name_truncation():
    long_name = "a" * 30
    models = [ModelUsage(model=f"org/{long_name}", spend=1.0)]
    text = _render_top_models(models, lang_zh=False, theme=THEME_MAP["blue-dark"], metric="spend")
    raw = str(text)
    assert long_name[:19] in raw
    assert "..." in raw


def test_render_top_models_multiple():
    models = [
        ModelUsage(model="anthropic/claude-opus-4", spend=3.5),
        ModelUsage(model="openai/gpt-4.1", spend=0.8),
    ]
    text = _render_top_models(models, lang_zh=False, theme=THEME_MAP["blue-dark"], metric="spend", chart_width=10)
    raw = str(text)
    assert "Top Models" in raw
    assert "claude-opus-4" in raw
    assert "gpt-4.1" in raw
    assert "$3.50" in raw.replace(" ", "")


def test_format_aggregated_results_with_openrouter_activity():
    results = {
        "openrouter": [
            ProviderUsage(
                provider="openrouter",
                label="Credits",
                used=10.0,
                limit=100.0,
                remaining=90.0,
                percent=10.0,
                reset_at=None,
                unit="$",
            ),
            ProviderUsage(
                provider="openrouter",
                label="Activity",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                activity_totals=ActivityTotals(
                    spend=4.3,
                    requests=45,
                    prompt_tokens=4500,
                    completion_tokens=2000,
                    reasoning_tokens=300,
                ),
            ),
            ProviderUsage(
                provider="openrouter",
                label="Daily Spend",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                daily_activity=[
                    DailyUsage(date="2026-06-10", models=[ModelUsage(model="anthropic/claude-opus-4", requests=10, spend=3.5)], total=3.5),
                    DailyUsage(date="2026-06-11", models=[ModelUsage(model="openai/gpt-4.1", requests=5, spend=0.8)], total=0.8),
                ],
            ),
            ProviderUsage(
                provider="openrouter",
                label="Top Models",
                used=0.0,
                limit=None,
                remaining=None,
                percent=None,
                reset_at=None,
                unit="text",
                top_models=[
                    ModelUsage(model="anthropic/claude-opus-4", spend=3.5, requests=10),
                    ModelUsage(model="openai/gpt-4.1", spend=0.8, requests=5),
                ],
            ),
        ]
    }
    text = _format_aggregated_results(results, {}, order=["openrouter"], lang_zh=False)
    raw = str(text)
    assert "OpenRouter" in raw
    assert "Credits" in raw
    assert "Req: 45" in raw
    assert "Daily Requests" in raw
    assert "Top Models" in raw
    assert "claude-opus-4" in raw
    assert "10" in raw


def test_build_model_color_map_stable_and_ordered():
    from kimi_code_usage.main import _build_model_color_map, _model_colors

    theme = THEME_MAP["blue-dark"]
    colors = _model_colors(theme)
    names = ["hy3", "nemotron-3-ultra", "laguna-m.1"]
    cmap = _build_model_color_map(names, theme)
    # Canonical order → color assigned by position
    assert cmap["hy3"] == colors[0]
    assert cmap["nemotron-3-ultra"] == colors[1]
    assert cmap["laguna-m.1"] == colors[2]
    # Deterministic for the same input
    assert _build_model_color_map(names, theme) == cmap
    # Colors cycle when there are more models than palette entries
    many = [f"m{i}" for i in range(len(colors) + 2)]
    cmap_many = _build_model_color_map(many, theme)
    assert cmap_many[f"m{len(colors)}"] == colors[0]
    assert cmap_many[f"m{len(colors) + 1}"] == colors[1]


def test_build_openrouter_color_map():
    from kimi_code_usage.main import _build_openrouter_color_map, _model_colors

    theme = THEME_MAP["blue-dark"]
    colors = _model_colors(theme)
    # Prefer the top_models row; rank by the displayed metric (tokens), not the row's spend order
    top_row = ProviderUsage(
        provider="openrouter", label="Top Models", used=0.0, limit=None, remaining=None,
        percent=None, reset_at=None, unit="text",
        top_models=[
            ModelUsage(model="laguna", spend=5.0, prompt_tokens=1_000_000),
            ModelUsage(model="hy3", spend=1.0, prompt_tokens=9_000_000),
        ],
    )
    cmap = _build_openrouter_color_map([top_row], metric="tokens", theme=theme)
    assert cmap["hy3"] == colors[0]      # 9M tokens → ranked first
    assert cmap["laguna"] == colors[1]   # 1M tokens → second

    # No model breakdown → None (e.g. non-OpenRouter providers)
    plain_row = ProviderUsage(provider="kimi", label="x", used=0.0, limit=None, remaining=None,
                              percent=None, reset_at=None, unit="text")
    assert _build_openrouter_color_map([plain_row], metric="tokens", theme=theme) is None

    # Falls back to daily_activity when there is no top_models row
    daily_row = ProviderUsage(
        provider="openrouter", label="Daily", used=0.0, limit=None, remaining=None,
        percent=None, reset_at=None, unit="text",
        daily_activity=[DailyUsage(date="2026-07-10",
                                   models=[ModelUsage(model="z", prompt_tokens=5_000_000)], total=0.0)],
    )
    assert _build_openrouter_color_map([daily_row], metric="tokens", theme=theme) == {"z": colors[0]}


def test_daily_and_top_models_share_colors():
    # Regression: the same model must get the same color in the daily legend and in Top Models,
    # even though the two charts sort models differently (tokens vs spend).
    from kimi_code_usage.main import _build_model_color_map

    theme = THEME_MAP["blue-dark"]
    color_map = _build_model_color_map(["hy3", "nemotron-3-ultra", "laguna-m.1"], theme)
    hy3_color = color_map["hy3"]
    assert hy3_color != color_map["laguna-m.1"]

    daily = [
        DailyUsage(date="2026-07-10",
                   models=[ModelUsage(model="hy3", prompt_tokens=9_000_000),
                           ModelUsage(model="laguna-m.1", prompt_tokens=1_000_000)],
                   total=0.0),
    ]
    daily_text = _render_daily_chart(daily, lang_zh=False, theme=theme, metric="tokens",
                                     days_window=7, color_map=color_map)
    daily_styles = {str(s.style) for s in daily_text.spans}
    assert hy3_color in daily_styles

    # Top Models receives the SAME map but a spend-descending list (laguna first).
    top = [
        ModelUsage(model="laguna-m.1", spend=5.0, prompt_tokens=1_000_000),
        ModelUsage(model="hy3", spend=1.0, prompt_tokens=9_000_000),
    ]
    top_text = _render_top_models(top, lang_zh=False, theme=theme, metric="tokens", color_map=color_map)
    top_styles = {str(s.style) for s in top_text.spans}
    assert hy3_color in top_styles


def test_window_top_models_respects_window_and_ranks_by_metric():
    from kimi_code_usage.main import _window_top_models

    daily = [
        DailyUsage(date="2026-07-08", models=[ModelUsage(model="old-only", requests=1000)], total=0.0),
        DailyUsage(date="2026-07-16", models=[ModelUsage(model="recent-a", requests=50)], total=0.0),
        DailyUsage(date="2026-07-17", models=[ModelUsage(model="recent-b", requests=80)], total=0.0),
    ]
    # 7-day window ends at the latest date (07-17) → covers 07-11..07-17, excludes 07-08
    windowed = _window_top_models(daily, days_window=7, metric="requests")
    assert [m.model for m in windowed] == ["recent-b", "recent-a"]  # ranked by requests desc
    assert all(m.model != "old-only" for m in windowed)

    # 30-day window includes all three, still ranked by the metric
    wide = _window_top_models(daily, days_window=30, metric="requests")
    assert [m.model for m in wide] == ["old-only", "recent-b", "recent-a"]

    # Same model on multiple days within the window is aggregated
    daily2 = [
        DailyUsage(date="2026-07-16", models=[ModelUsage(model="x", requests=30, prompt_tokens=1000)], total=0.0),
        DailyUsage(date="2026-07-17", models=[ModelUsage(model="x", requests=20, prompt_tokens=2000)], total=0.0),
    ]
    agg = _window_top_models(daily2, days_window=7, metric="requests")
    assert len(agg) == 1
    assert agg[0].requests == 50
    assert agg[0].prompt_tokens == 3000

    # No dated activity → empty list
    assert _window_top_models([], days_window=7, metric="requests") == []


def test_fit_scroll_body():
    from kimi_code_usage.main import _fit_scroll_body

    # Fits within budget → returned unchanged, offset reset to 0
    small = Text("\n".join(f"line{i}" for i in range(5)))
    out, off = _fit_scroll_body(small, budget=10, scroll_offset=3, lang_zh=False)
    assert out is small
    assert off == 0

    # Overflow → view_rows = budget-1 content lines + 1 indicator line
    big = Text("\n".join(f"L{i}" for i in range(20)))
    out, off = _fit_scroll_body(big, budget=10, scroll_offset=0, lang_zh=False)
    lines = out.plain.split("\n")
    assert len(lines) == 10           # 9 content + 1 indicator
    assert "L0" in lines[0]
    assert "▼" in lines[-1] and "/20" in lines[-1]  # more below, position shown
    assert "▲" not in lines[-1]                      # at top → no up arrow

    # Offset beyond the end clamps to max, last content line is the final one
    out2, off2 = _fit_scroll_body(big, budget=10, scroll_offset=999, lang_zh=False)
    assert off2 == 20 - 9             # max_off = total - view_rows
    lines2 = out2.plain.split("\n")
    assert "L19" in lines2[-2]
    assert "▲" in lines2[-1] and "▼" not in lines2[-1]  # at bottom → only up arrow

    # Middle offset shows both arrows and honors the offset
    out3, off3 = _fit_scroll_body(big, budget=10, scroll_offset=5, lang_zh=False)
    assert off3 == 5
    indicator3 = out3.plain.split("\n")[-1]
    assert "▲" in indicator3 and "▼" in indicator3

    # Localized scroll label
    out_zh, _ = _fit_scroll_body(big, budget=10, scroll_offset=0, lang_zh=True)
    assert "滚动" in out_zh.plain.split("\n")[-1]
