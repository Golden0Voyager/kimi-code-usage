import asyncio
import json
import os
import socket

from aiohttp import web

from kimi_code_usage.config import ConfigResolver
from kimi_code_usage.providers import dispatch_all

LANG = os.getenv("LANG", "en")
IS_ZH = "zh" in LANG.lower()


def _get_lan_ip() -> str:
    try:
        # Try common LAN subnets first (fast path)
        ifaces = socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET)
        seen = set()
        for addr in ifaces:
            ip = addr[4][0]
            if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172.16."):
                return ip
            seen.add(ip)
        for ip in seen:
            if ip != "127.0.0.1":
                return ip
    except Exception:
        pass

    # Fallback: connect to public DNS
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip != "127.0.0.1":
                return ip
    except Exception:
        pass

    return "127.0.0.1"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{title}</title>
<style>
:root {{
    --bg: #0f0f1a;
    --text: #e0e0e0;
    --card-bg: #1a1a2e;
    --border: #2a2a3e;
    --label: #aaa;
    --meta: #666;
    --title: #fff;
    --bar-bg: #2a2a3e;
    --input-bg: #2a2a3e;
    --input-text: #e0e0e0;
    --switch-off: #444;
}}
[data-theme="light"] {{
    --bg: #f0f0f0;
    --text: #333;
    --card-bg: #fff;
    --border: #ddd;
    --label: #666;
    --meta: #999;
    --title: #111;
    --bar-bg: #e0e0e0;
    --input-bg: #e0e0e0;
    --input-text: #333;
    --switch-off: #ccc;
}}
[data-theme="sky"] {{
    --bg: #0a1628;
    --text: #c8d6e5;
    --card-bg: #12203a;
    --border: #1e3357;
    --label: #8395a7;
    --meta: #576574;
    --title: #fff;
    --bar-bg: #1e3357;
    --input-bg: #1e3357;
    --input-text: #c8d6e5;
    --switch-off: #2d4a6a;
}}
[data-theme="mono"] {{
    --bg: #111;
    --text: #ccc;
    --card-bg: #1a1a1a;
    --border: #333;
    --label: #888;
    --meta: #555;
    --title: #fff;
    --bar-bg: #333;
    --input-bg: #333;
    --input-text: #ccc;
    --switch-off: #444;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, 'Helvetica Neue', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 16px;
    min-height: 100vh;
    transition: background 0.3s, color 0.3s;
}}
h1 {{
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--title);
    margin-bottom: 4px;
}}
.header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 8px;
}}
.subtitle {{
    font-size: 0.8rem;
    color: var(--meta);
}}
.provider {{
    background: var(--card-bg);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    transition: background 0.3s;
}}
.provider-title {{
    font-size: 1rem;
    font-weight: 600;
    color: var(--title);
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}}
.quota-row {{
    display: flex;
    align-items: center;
    padding: 6px 0;
    gap: 8px;
    flex-wrap: wrap;
}}
.quota-label {{
    font-size: 0.85rem;
    color: var(--label);
    min-width: 90px;
    flex-shrink: 0;
}}
.quota-bar-wrap {{
    flex: 1;
    min-width: 120px;
    height: 18px;
    background: var(--bar-bg);
    border-radius: 9px;
    overflow: hidden;
}}
.quota-bar {{
    height: 100%;
    border-radius: 9px;
    transition: width 0.5s ease;
}}
.quota-text {{
    font-size: 0.85rem;
    font-weight: 500;
    min-width: 60px;
    max-width: 45%;
    text-align: right;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.quota-meta {{
    font-size: 0.75rem;
    color: var(--meta);
    width: 100%;
    padding-left: 98px;
    margin-top: -2px;
    margin-bottom: 4px;
}}
.status-ok {{ background: #22c55e; }}
.status-warn {{ background: #eab308; }}
.status-danger {{ background: #ef4444; }}
.error-box {{
    background: #2a1a1a;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    color: #ef4444;
    font-size: 0.85rem;
}}
.no-data {{
    text-align: center;
    color: var(--meta);
    padding: 40px 0;
    font-size: 0.9rem;
}}
.btn {{
    background: var(--input-bg);
    color: var(--text);
    border: none;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 0.8rem;
    cursor: pointer;
}}
.btn:hover {{ opacity: 0.8; }}
.spinner {{
    text-align: center;
    padding: 60px 0;
    color: var(--meta);
}}
.footer {{ text-align: center; font-size: 0.7rem; color: var(--meta); margin-top: 20px; }}

/* ── Settings panel ── */
.settings-toggle {{
    background: none;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--meta);
    font-size: 1.2rem;
    cursor: pointer;
    padding: 4px 10px;
    line-height: 1;
}}
.settings-toggle:hover {{ color: var(--text); border-color: var(--label); }}
.settings-panel {{
    display: none;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
    transition: background 0.3s;
}}
.settings-panel.open {{ display: block; }}
.settings-title {{
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--title);
    margin-bottom: 12px;
}}
.setting-group {{
    margin-bottom: 14px;
}}
.setting-label {{
    font-size: 0.8rem;
    color: var(--label);
    margin-bottom: 6px;
}}
.theme-options {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}}
.theme-btn {{
    background: var(--input-bg);
    color: var(--text);
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 0.8rem;
    cursor: pointer;
}}
.theme-btn.active {{ border-color: #60a5fa; }}
.provider-check {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    font-size: 0.85rem;
    color: var(--text);
    cursor: pointer;
}}
.provider-check input {{
    width: 16px;
    height: 16px;
    accent-color: #60a5fa;
}}

/* ── Activity summary ── */
.act-summary {{
    font-size: 0.82rem;
    color: var(--label);
    padding: 4px 0 8px 0;
    line-height: 1.6;
}}
.act-summary span {{
    margin-right: 12px;
}}

/* ── Daily chart ── */
.chart-section {{
    margin-top: 10px;
    margin-bottom: 6px;
}}
.chart-title {{
    font-size: 0.82rem;
    color: var(--meta);
    margin-bottom: 6px;
}}
.chart-cols {{
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 80px;
    padding: 0 2px;
}}
.chart-col {{
    flex: 1;
    display: flex;
    flex-direction: column-reverse;
    border-radius: 2px 2px 0 0;
    overflow: hidden;
    min-height: 2px;
}}
.chart-col-seg {{
    width: 100%;
    flex-shrink: 0;
}}
.chart-labels {{
    display: flex;
    gap: 2px;
    margin-top: 2px;
}}
.chart-labels span {{
    flex: 1;
    font-size: 0.6rem;
    color: var(--meta);
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

/* ── Top models ── */
.tm-section {{
    margin-top: 10px;
}}
.tm-title {{
    font-size: 0.82rem;
    color: var(--meta);
    margin-bottom: 6px;
}}
.tm-row {{
    display: flex;
    align-items: center;
    padding: 3px 0;
    gap: 6px;
}}
.tm-name {{
    font-size: 0.78rem;
    color: var(--label);
    width: 100px;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}
.tm-val {{
    font-size: 0.78rem;
    color: var(--meta);
    width: 60px;
    text-align: right;
    flex-shrink: 0;
}}
.tm-bar-wrap {{
    flex: 1;
    height: 14px;
    background: var(--bar-bg);
    border-radius: 3px;
    overflow: hidden;
}}
.tm-bar {{
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}}

/* ── Legend ── */
.legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
}}
.legend-item {{
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.72rem;
    color: var(--meta);
}}
.legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
}}
</style>
</head>
<body>
<div class="header">
    <div>
        <h1>{title}</h1>
        <div class="subtitle" id="lastUpdate">-</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
        <button class="settings-toggle" onclick="toggleSettings()" id="settingsBtn">⚙</button>
        <button class="btn" onclick="refresh()">{refresh_label}</button>
    </div>
</div>
<div id="settingsPanel" class="settings-panel">
    <div class="settings-title">{settings_label}</div>
    <div class="setting-group">
        <div class="setting-label">{theme_label}</div>
        <div class="theme-options" id="themeOptions">
            <button class="theme-btn" data-theme="dark" onclick="setTheme('dark')">Dark</button>
            <button class="theme-btn" data-theme="light" onclick="setTheme('light')">Light</button>
            <button class="theme-btn" data-theme="sky" onclick="setTheme('sky')">Sky</button>
            <button class="theme-btn" data-theme="mono" onclick="setTheme('mono')">Mono</button>
        </div>
    </div>
    <div class="setting-group">
        <div class="setting-label">{providers_label}</div>
        <div id="providerToggles"></div>
    </div>
</div>
<div id="content"><div class="spinner">{loading_label}</div></div>
<div class="footer" id="footer"></div>
<script>
var CHART_COLORS = [
    '#22c55e', '#eab308', '#ef4444', '#60a5fa', '#a78bfa',
    '#fb923c', '#2dd4bf', '#f472b6', '#4ade80', '#facc15'
];
var ALL_PROVIDERS = {provider_json};

// ── Settings ──
function loadSettings() {{
    try {{
        var s = localStorage.getItem('kimi_dash_settings');
        if (s) return JSON.parse(s);
    }} catch(e) {{}}
    return {{ theme: 'dark', hidden: {{}} }};
}}
function saveSettings(s) {{
    try {{ localStorage.setItem('kimi_dash_settings', JSON.stringify(s)); }} catch(e) {{}}
}}
var settings = loadSettings();

function applyTheme(theme) {{
    document.body.setAttribute('data-theme', theme);
    document.querySelectorAll('#themeOptions .theme-btn').forEach(function(b) {{
        b.classList.toggle('active', b.getAttribute('data-theme') === theme);
    }});
}}
function setTheme(theme) {{
    settings.theme = theme;
    saveSettings(settings);
    applyTheme(theme);
}}
function toggleSettings() {{
    var p = document.getElementById('settingsPanel');
    p.classList.toggle('open');
    buildProviderToggles();
}}
function buildProviderToggles() {{
    var el = document.getElementById('providerToggles');
    if (!el) return;
    if (!settings.hidden) settings.hidden = {{}};
    var html = '';
    ALL_PROVIDERS.forEach(function(p) {{
        var checked = !settings.hidden[p];
        html += '<label class="provider-check">';
        html += '<input type="checkbox" data-provider="' + p + '" ' + (checked ? 'checked' : '') + '>';
        html += providerLabel(p);
        html += '</label>';
    }});
    el.innerHTML = html;
    // Bind change events
    el.querySelectorAll('input[type=checkbox]').forEach(function(cb) {{
        cb.addEventListener('change', function() {{
            toggleProvider(this.getAttribute('data-provider'), this.checked);
        }});
    }});
}}
function toggleProvider(p, show) {{
    if (show) delete settings.hidden[p];
    else settings.hidden[p] = true;
    saveSettings(settings);
    refresh();
}}
function isProviderVisible(p) {{
    return !settings.hidden || !settings.hidden[p];
}}

// ── Helpers ──
function shortDate(s) {{ return s && s.length >= 10 ? s.slice(5,10) : s; }}
function fmt(n) {{
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n/1000).toFixed(1) + 'K';
    return n.toLocaleString();
}}
function fmtDollar(n) {{ return '$' + n.toFixed(2); }}
function esc(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function providerLabel(p) {{
    var map = {{ 'kimi': '{kimi_label}', 'openai': '{openai_label}', 'anthropic': '{anthropic_label}', 'openrouter': '{openrouter_label}' }};
    return map[p] || p.charAt(0).toUpperCase() + p.slice(1);
}}

// ── Render chart ──
function renderDailyChart(days, metric) {{
    metric = metric || 'requests';
    if (!days || days.length === 0) return '';
    var html = '<div class="chart-section"><div class="chart-title">{chart_daily_label}</div>';

    var dayVals = days.map(function(d) {{
        var total = 0;
        (d.models || []).forEach(function(m) {{
            if (metric === 'requests') total += m.requests || 0;
            else if (metric === 'tokens') total += (m.prompt_tokens||0) + (m.completion_tokens||0) + (m.reasoning_tokens||0);
            else total += m.spend || 0;
        }});
        return total;
    }});
    var maxVal = Math.max.apply(null, dayVals) || 1;
    var height = 80;

    var modelTotals = {{}};
    days.forEach(function(d) {{
        (d.models || []).forEach(function(m) {{
            var v = metric === 'requests' ? (m.requests||0) : metric === 'tokens' ? (m.prompt_tokens||0)+(m.completion_tokens||0)+(m.reasoning_tokens||0) : (m.spend||0);
            modelTotals[m.model] = (modelTotals[m.model] || 0) + v;
        }});
    }});
    var topModels = Object.keys(modelTotals).sort(function(a,b) {{ return modelTotals[b] - modelTotals[a]; }}).slice(0, 6);
    var topSet = {{}};
    topModels.forEach(function(m) {{ topSet[m] = true; }});
    var othersIdx = topModels.length % CHART_COLORS.length;

    html += '<div class="chart-cols">';
    days.forEach(function(d) {{
        var segs = [];
        var othersTotal = 0;
        (d.models || []).forEach(function(m) {{
            var v = metric === 'requests' ? (m.requests||0) : metric === 'tokens' ? (m.prompt_tokens||0)+(m.completion_tokens||0)+(m.reasoning_tokens||0) : (m.spend||0);
            if (topSet[m.model]) segs.push({{ colorIdx: topModels.indexOf(m.model), val: v }});
            else othersTotal += v;
        }});
        if (othersTotal > 0) segs.push({{ colorIdx: othersIdx, val: othersTotal }});
        if (segs.length === 0) segs.push({{ colorIdx: 0, val: 0 }});

        var dayTotal = segs.reduce(function(s, seg) {{ return s + seg.val; }}, 0);
        var colH = dayTotal > 0 ? Math.max(2, Math.round(dayTotal / maxVal * height)) : 2;
        html += '<div class="chart-col" style="height:' + colH + 'px">';
        segs.sort(function(a,b) {{ return b.val - a.val; }});
        segs.forEach(function(seg) {{
            var segH = seg.val / dayTotal * colH;
            if (segH < 1 && seg.val > 0) segH = 1;
            html += '<div class="chart-col-seg" style="height:' + segH + 'px;background:' + CHART_COLORS[seg.colorIdx % CHART_COLORS.length] + '"></div>';
        }});
        html += '</div>';
    }});
    html += '</div><div class="chart-labels">';
    days.forEach(function(d) {{ html += '<span>' + esc(shortDate(d.date)) + '</span>'; }});
    html += '</div>';

    if (topModels.length > 0) {{
        html += '<div class="legend">';
        topModels.forEach(function(m, i) {{
            var short = m.indexOf('/') >= 0 ? m.split('/').pop() : m;
            if (short.length > 16) short = short.slice(0,13) + '...';
            html += '<div class="legend-item"><div class="legend-dot" style="background:' + CHART_COLORS[i % CHART_COLORS.length] + '"></div>' + esc(short) + '</div>';
        }});
        html += '<div class="legend-item"><div class="legend-dot" style="background:' + CHART_COLORS[othersIdx % CHART_COLORS.length] + '"></div>{others_label}</div>';
        html += '</div>';
    }}
    html += '</div>';
    return html;
}}

function renderTopModels(models, metric) {{
    metric = metric || 'requests';
    if (!models || models.length === 0) return '';
    var maxVal = 1;
    models.forEach(function(m) {{
        var v = metric === 'requests' ? (m.requests||0) : metric === 'tokens' ? (m.prompt_tokens||0)+(m.completion_tokens||0)+(m.reasoning_tokens||0) : (m.spend||0);
        if (v > maxVal) maxVal = v;
    }});
    var html = '<div class="tm-section"><div class="tm-title">{top_models_label}</div>';
    models.slice(0, 7).forEach(function(m, i) {{
        var v = metric === 'requests' ? (m.requests||0) : metric === 'tokens' ? (m.prompt_tokens||0)+(m.completion_tokens||0)+(m.reasoning_tokens||0) : (m.spend||0);
        var pct = v / maxVal * 100;
        var short = m.model.indexOf('/') >= 0 ? m.model.split('/').pop() : m.model;
        if (short.length > 18) short = short.slice(0,15) + '...';
        var valStr = metric === 'requests' ? v.toLocaleString() : metric === 'tokens' ? fmt(v) : fmtDollar(v);
        html += '<div class="tm-row"><div class="tm-name">' + esc(short) + '</div><div class="tm-val">' + valStr + '</div><div class="tm-bar-wrap"><div class="tm-bar" style="width:' + pct + '%;background:' + CHART_COLORS[i % CHART_COLORS.length] + '"></div></div></div>';
    }});
    html += '</div>';
    return html;
}}

// ── Render item ──
function renderItem(item) {{
    if (item.activity_totals || item.daily_activity || item.top_models) {{
        var html = '<div class="quota-row"><div class="quota-label">' + esc(item.label) + '</div>';
        if (item.limit !== null && item.limit > 0) {{
            var pct = item.percent || 0;
            var status = pct < 50 ? 'status-ok' : pct < 80 ? 'status-warn' : 'status-danger';
            html += '<div class="quota-bar-wrap"><div class="quota-bar ' + status + '" style="width:' + Math.min(100, pct) + '%"></div></div>';
            html += '<div class="quota-text">' + (item.unit === '$' ? fmtDollar(item.used) + ' / ' + fmtDollar(item.limit) : fmt(item.used) + ' / ' + fmt(item.limit)) + '</div>';
        }} else {{
            html += '<div class="quota-bar-wrap" style="flex:0.3;min-width:60px"></div>';
            html += '<div class="quota-text">' + (item.unit === '$' ? fmtDollar(item.used) : item.unit === 'text' ? esc(item.text_value||'') : fmt(item.used)) + '</div>';
        }}
        html += '</div>';

        if (item.activity_totals) {{
            var t = item.activity_totals;
            var parts = [];
            if (t.requests) parts.push('Req: ' + t.requests.toLocaleString());
            if (t.prompt_tokens || t.completion_tokens) {{
                var tok = 'In: ' + fmt(t.prompt_tokens) + ' / Out: ' + fmt(t.completion_tokens);
                if (t.reasoning_tokens) tok += ' (+ ' + fmt(t.reasoning_tokens) + ' reason)';
                parts.push(tok);
            }}
            if (t.spend) parts.push('Spend: ' + fmtDollar(t.spend));
            html += '<div class="act-summary">' + parts.join(' &nbsp;|&nbsp; ') + '</div>';
        }}
        if (item.daily_activity) html += renderDailyChart(item.daily_activity, 'requests');
        if (item.top_models) html += renderTopModels(item.top_models, 'requests');
        if (item.countdown) html += '<div class="quota-meta" style="padding-left:0;margin-top:8px">{reset_label}: ' + esc(item.countdown) + '</div>';
        if (item.reset_at) html += '<div class="quota-meta" style="padding-left:0">{reset_time_label}: ' + esc(item.reset_at) + '</div>';
        return html;
    }}

    var pct = item.percent;
    var status = pct === null ? 'status-ok' : pct < 50 ? 'status-ok' : pct < 80 ? 'status-warn' : 'status-danger';
    var barW = pct === null ? 0 : Math.min(100, pct);
    var html = '<div class="quota-row"><div class="quota-label">' + esc(item.label) + '</div>';
    html += '<div class="quota-bar-wrap"><div class="quota-bar ' + status + '" style="width:' + barW + '%"></div></div>';
    if (item.limit !== null && item.limit > 0) {{
        html += '<div class="quota-text">' + (item.unit === '$' ? fmtDollar(item.used) + ' / ' + fmtDollar(item.limit) : fmt(item.used) + ' / ' + fmt(item.limit)) + '</div>';
    }} else {{
        html += '<div class="quota-text">' + (item.unit === '$' ? fmtDollar(item.used) : item.unit === 'text' ? esc(item.text_value||'') : fmt(item.used)) + '</div>';
    }}
    html += '</div>';
    if (item.countdown) html += '<div class="quota-meta">{reset_label}: ' + esc(item.countdown) + '</div>';
    if (item.reset_at) html += '<div class="quota-meta">{reset_time_label}: ' + esc(item.reset_at) + '</div>';
    return html;
}}

// ── Main render ──
function render(data) {{
    var html = '';
    var now = new Date();
    document.getElementById('lastUpdate').textContent = '{updated_label}: ' + now.toLocaleString();
    var hasAny = false;
    var order = {provider_order_json};

    for (var pi = 0; pi < order.length; pi++) {{
        var p = order[pi];
        if (!isProviderVisible(p)) continue;
        var items = data.results[p];
        var err = data.errors[p];
        if (!items && !err) continue;
        hasAny = true;
        html += '<div class="provider"><div class="provider-title">' + providerLabel(p) + '</div>';
        if (err) {{
            html += '<div class="error-box">' + esc(err) + '</div>';
        }} else {{
            for (var ii = 0; ii < items.length; ii++) {{
                html += renderItem(items[ii]);
            }}
        }}
        html += '</div>';
    }}

    document.getElementById('content').innerHTML = hasAny ? html : '<div class="no-data">{no_data_label}</div>';
}}

async function refresh() {{
    try {{
        var r = await fetch('/api/usage');
        var data = await r.json();
        render(data);
    }} catch(e) {{
        document.getElementById('content').innerHTML = '<div class="error-box">' + e.message + '</div>';
    }}
}}

// ── Init ──
applyTheme(settings.theme);
refresh();
setInterval(refresh, {refresh_interval});
</script>
</body>
</html>"""


_PROVIDER_ORDER = ["kimi", "openai", "anthropic", "openrouter"]

def _build_html(lang_zh: bool) -> str:
    provider_json = json.dumps(_PROVIDER_ORDER)
    order_json = json.dumps(_PROVIDER_ORDER)
    if lang_zh:
        return HTML_TEMPLATE.format(
            lang="zh",
            title="AI 用量配额看板",
            refresh_label="刷新",
            loading_label="加载中...",
            updated_label="上次更新",
            reset_label="重置倒计时",
            reset_time_label="重置时间",
            no_data_label="未找到用量数据，或未配置任何服务商",
            settings_label="设置",
            theme_label="主题",
            providers_label="显示提供商",
            chart_daily_label="每日用量",
            top_models_label="Top 模型",
            others_label="其他",
            kimi_label="Kimi Code",
            openai_label="OpenAI",
            anthropic_label="Anthropic",
            openrouter_label="OpenRouter",
            provider_json=provider_json,
            provider_order_json=order_json,
            refresh_interval="180000",
        )
    else:
        return HTML_TEMPLATE.format(
            lang="en",
            title="AI Quota Dashboard",
            refresh_label="Refresh",
            loading_label="Loading...",
            updated_label="Last updated",
            reset_label="Reset in",
            reset_time_label="Reset at",
            no_data_label="No usage data found or no providers configured",
            settings_label="Settings",
            theme_label="Theme",
            providers_label="Show Providers",
            chart_daily_label="Daily Usage",
            top_models_label="Top Models",
            others_label="Others",
            kimi_label="Kimi Code",
            openai_label="OpenAI",
            anthropic_label="Anthropic",
            openrouter_label="OpenRouter",
            provider_json=provider_json,
            provider_order_json=order_json,
            refresh_interval="180000",
        )


async def handle_index(request: web.Request) -> web.Response:
    lang_zh = "zh" in request.headers.get("Accept-Language", "").lower() or IS_ZH
    return web.Response(text=_build_html(lang_zh), content_type="text/html")


def _item_to_dict(item):
    d = {
        "label": item.label,
        "used": item.used,
        "limit": item.limit,
        "remaining": item.remaining,
        "percent": item.percent,
        "unit": item.unit,
        "countdown": item.countdown,
        "reset_at": item.reset_at,
        "text_value": item.text_value,
    }
    if item.activity_totals:
        t = item.activity_totals
        d["activity_totals"] = {
            "spend": t.spend, "requests": t.requests,
            "prompt_tokens": t.prompt_tokens,
            "completion_tokens": t.completion_tokens,
            "reasoning_tokens": t.reasoning_tokens,
        }
    if item.daily_activity:
        d["daily_activity"] = [
            {
                "date": da.date,
                "total": da.total,
                "models": [
                    {"model": m.model, "spend": m.spend, "requests": m.requests,
                     "prompt_tokens": m.prompt_tokens,
                     "completion_tokens": m.completion_tokens,
                     "reasoning_tokens": m.reasoning_tokens}
                    for m in da.models
                ],
            }
            for da in item.daily_activity
        ]
    if item.top_models:
        d["top_models"] = [
            {"model": m.model, "spend": m.spend, "requests": m.requests,
             "prompt_tokens": m.prompt_tokens,
             "completion_tokens": m.completion_tokens,
             "reasoning_tokens": m.reasoning_tokens}
            for m in item.top_models
        ]
    return d


async def handle_api(request: web.Request) -> web.Response:
    resolver = ConfigResolver()
    config = resolver.resolve()
    results, errors = await dispatch_all(config)
    return web.json_response({
        "results": {p: [_item_to_dict(item) for item in items] for p, items in results.items()},
        "errors": errors,
    })


async def run_server(port: int = 8765, lang_zh: bool = IS_ZH) -> None:
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/usage", handle_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    lan_ip = _get_lan_ip()
    print(f"  {'启动成功' if lang_zh else 'Server started'}: http://0.0.0.0:{port}")
    print(f"  {'局域网访问' if lang_zh else 'LAN access'}: http://{lan_ip}:{port}")
    print(f"  {'按 Ctrl-C 停止' if lang_zh else 'Press Ctrl-C to stop'}")
    print()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
