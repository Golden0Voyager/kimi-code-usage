import * as vscode from 'vscode';
import * as path from 'path';
import type { SnapshotStore } from './storage';
import { predictExhaustion, type Prediction } from './predict';
import { DEFAULT_HISTORY_RETENTION_DAYS, type Snapshot, type WindowType } from './types';
import { currentLang, t } from './i18n';
import { localizedLimitName } from './api';
import { readHistoryRetentionDays } from './config';

const VIEW_TYPE = 'kimiCodeUsage.history';
const DAY_MS = 24 * 3600 * 1000;

interface Series {
  windowType: WindowType;
  label: string;
  points: Array<{
    ts: number;
    label: string;
    percent_left: number;
    used: number;
    limit: number;
    paceRatio: number | null;
  }>;
  prediction: Prediction;
}

interface Payload {
  generatedAt: number;
  series: Series[];
  sampleSize: number;
  retentionDays: number;
}

export class HistoryPanel {
  private panel: vscode.WebviewPanel | undefined;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly store: SnapshotStore,
  ) {}

  show(): void {
    if (this.panel) {
      this.panel.reveal();
      void this.refresh();
      return;
    }

    this.panel = vscode.window.createWebviewPanel(VIEW_TYPE, t('Usage History'), vscode.ViewColumn.One, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.file(this.mediaDir())],
    });

    this.panel.onDidDispose(() => {
      this.panel = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (msg) => {
      if (msg?.type === 'requestData') {
        await this.refresh();
      }
    });

    this.panel.webview.html = this.renderHtml();
    void this.refresh();
  }

  private mediaDir(): string {
    return this.context.asAbsolutePath('out/media');
  }

  private mediaPath(): string {
    return path.join(this.mediaDir(), 'chart.umd.js');
  }

  private async refresh(): Promise<void> {
    if (!this.panel) return;
    const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
    const retentionDays = readHistoryRetentionDays(cfg);
    const snapshots = await this.store.list({ sinceMs: Date.now() - retentionDays * DAY_MS });
    if (!this.panel) return;
    const payload = buildPayload(snapshots, retentionDays);
    const isDark =
      vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.Dark ||
      vscode.window.activeColorTheme.kind === vscode.ColorThemeKind.HighContrast;
    await this.panel.webview.postMessage({ type: 'data', payload, isDark });
  }

  private renderHtml(): string {
    const scriptUri = this.panel!.webview.asWebviewUri(vscode.Uri.file(this.mediaPath()));
    const scriptUriJson = JSON.stringify(String(scriptUri));
    const cspSource = this.panel!.webview.cspSource;
    const htmlLang = escapeHtml(currentLang());
    const i18n = {
      remainingPercent: escapeHtml(t('Remaining %')),
      paceRatio: escapeHtml(t('Pace Ratio')),
      time: escapeHtml(t('Time')),
      trend: escapeHtml(t('Trend')),
      predictedExhaustion: escapeHtml(t('Predicted Exhaustion')),
      usage: escapeHtml(t('Usage')),
      alreadyExceeded: escapeHtml(t('Already exceeded')),
      noHistory: escapeHtml(t('No history yet — leave the extension running for a few refreshes.')),
      chartLoadFailed: escapeHtml(
        t('Chart library failed to load. Please check the extension installation.'),
      ),
      perDay: escapeHtml(t('per-day')),
      dayShort: escapeHtml(t('day-short')),
      hourShort: escapeHtml(t('hour-short')),
      increasing: escapeHtml(t('increasing')),
      decreasing: escapeHtml(t('decreasing')),
      stable: escapeHtml(t('stable')),
      high: escapeHtml(t('high')),
      medium: escapeHtml(t('medium')),
      low: escapeHtml(t('low')),
      none: escapeHtml(t('none')),
      snapshots: escapeHtml(t('snapshots')),
      confidence: escapeHtml(t('confidence')),
      consumingFast: escapeHtml(t('Consuming fast')),
      slowingDown: escapeHtml(t('Slowing down')),
      steady: escapeHtml(t('Steady')),
      burningFast: escapeHtml(t('Burning fast')),
      onTrack: escapeHtml(t('On track')),
      recovering: escapeHtml(t('Recovering')),
      about: escapeHtml(t('about')),
      untilExhausted: escapeHtml(t('until exhausted')),
      minuteShort: escapeHtml(t('minute-short')),
    };
    return `<!DOCTYPE html>
	<html lang="${htmlLang}">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${cspSource} 'unsafe-inline'; style-src 'unsafe-inline'; img-src ${cspSource} data:;" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(t('Usage History'))}</title>
  <style>
    :root {
      color-scheme: light dark;
      --fg: var(--vscode-foreground);
      --bg: var(--vscode-editor-background);
      --muted: var(--vscode-descriptionForeground);
      --card: var(--vscode-editorWidget-background, var(--vscode-editor-background));
      --card-alt: var(--vscode-sideBar-background, var(--vscode-editorWidget-background, var(--vscode-editor-background)));
      --border: var(--vscode-widgetBorder, rgba(128,128,128,0.2));
      --accent: var(--vscode-textLink-foreground);
      --warn: var(--vscode-editorWarning-foreground, #cca700);
      --err: var(--vscode-errorForeground, #f48771);
      --ok: var(--vscode-testing-iconPassed, #3fb950);
      --row-hover: var(--vscode-list-hoverBackground, rgba(128,128,128,0.08));
      --stat-bg: rgba(127,127,127,0.06);
      --stat-warn-bg: rgba(204,167,0,0.10);
      --stat-warn-border: rgba(204,167,0,0.45);
    }
    * { box-sizing: border-box; }
    body {
      font-family: var(--vscode-font-family);
      color: var(--fg);
      background: var(--bg);
      margin: 0;
      padding: 18px 24px 24px;
    }
    h1 { font-size: 18px; line-height: 1.35; margin: 0 0 4px; font-weight: 600; letter-spacing: 0; }
    .sub { color: var(--muted); font-size: 12px; line-height: 1.5; margin-bottom: 18px; }
	    .history-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-items: start; max-width: 1120px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; min-width: 0; }
    .card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 12px; }
    .card-title { min-width: 0; }
    .card-title strong { display: block; font-size: 14px; line-height: 1.35; font-weight: 600; overflow-wrap: anywhere; }
    .card-meta { color: var(--muted); font-size: 11px; line-height: 1.4; margin-top: 3px; }
    .metric { flex: 0 0 auto; min-width: 76px; text-align: right; }
    .metric span { display: block; color: var(--muted); font-size: 10px; line-height: 1.2; text-transform: uppercase; }
    .metric strong { display: block; margin-top: 2px; font-size: 20px; line-height: 1; font-weight: 700; color: var(--accent); }
    .pill { display: inline-flex; align-items: center; max-width: 100%; padding: 2px 8px; border-radius: 999px; font-size: 11px; line-height: 1.4; font-weight: 500; background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); }
    .chart-wrap {
      position: relative;
	      height: 320px;
      min-height: 260px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 10px 4px;
      background: var(--card-alt);
    }
    .empty { color: var(--muted); font-style: italic; padding: 32px 0; text-align: center; }
    .stats-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    .stat { min-width: 0; border: 1px solid var(--border); border-radius: 8px; padding: 10px; background: var(--stat-bg); }
    .stat.warn { border-color: var(--stat-warn-border); background: var(--stat-warn-bg); }
    .stat-label { color: var(--muted); font-size: 11px; line-height: 1.3; margin-bottom: 5px; overflow-wrap: anywhere; }
    .stat-value { font-size: 13px; line-height: 1.35; font-weight: 600; overflow-wrap: anywhere; }
    .stat-value.warn { color: var(--warn); }
    details { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 10px; }
    summary { color: var(--muted); cursor: pointer; font-size: 12px; line-height: 1.4; outline-offset: 2px; }
    summary:hover { color: var(--fg); }
    summary:focus-visible { outline: 1px solid var(--vscode-focusBorder); }
    .table-wrap { overflow-x: auto; margin-top: 8px; }
    table { width: 100%; min-width: 420px; border-collapse: collapse; font-size: 12px; line-height: 1.35; }
    th, td { padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
    th:first-child, td:first-child { text-align: left; }
    th { color: var(--muted); font-weight: 500; background: var(--card-alt); }
    tr:hover td { background: var(--row-hover); }
    .footer { color: var(--muted); font-size: 11px; line-height: 1.4; margin-top: 14px; }
    @media (max-width: 560px) {
      body { padding: 14px; }
	      .history-grid { grid-template-columns: 1fr; gap: 12px; max-width: none; }
      .card { padding: 12px; }
      .card-header { flex-direction: column; align-items: stretch; gap: 8px; }
      .metric { text-align: left; min-width: 0; }
      .chart-wrap { height: 260px; padding: 8px 6px 2px; }
      .stats-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <h1>${escapeHtml(t('Usage History'))}</h1>
  <div class="sub">${escapeHtml(t('Snapshots are stored locally. Auto-pruned after retention period.'))}</div>
  <div id="root"><div class="empty">${escapeHtml(t('Loading...'))}</div></div>
  <script>
    const vscode = acquireVsCodeApi();
    const i18n = ${JSON.stringify(i18n)};
    const root = document.getElementById('root');
    const charts = [];
    let pendingPayload = null;
    let pendingIsDark = false;
    let chartReady = false;

    function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    function isFiniteNumber(v) { return typeof v === 'number' && Number.isFinite(v); }
    function fmtPct(v) { return isFiniteNumber(v) ? v.toFixed(1) + '%' : '—'; }
    function fmtWholePct(v) { return isFiniteNumber(v) ? Math.round(v) + '%' : '—'; }
    function fmtUsage(used, limit) {
      if (!isFiniteNumber(used) || !isFiniteNumber(limit) || limit <= 0) return '—';
      return Math.round(used).toLocaleString() + ' / ' + Math.round(limit).toLocaleString();
    }
    function fmtPace(v) { return isFiniteNumber(v) ? v.toFixed(2) : '—'; }
    function fmtDate(ms) {
      if (!ms) return '—';
      const d = new Date(ms);
      return d.toLocaleString();
    }
    function fmtAxisTime(ms) {
      if (!isFiniteNumber(Number(ms))) return '';
      return new Date(Number(ms)).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    }
    function fmtExhaustion(ms) {
      if (!ms) return '—';
      const diff = ms - Date.now();
      if (diff <= 0) return i18n.alreadyExceeded;
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const minutes = Math.floor((diff % 3600000) / 60000);
      let relative = '';
      if (days > 0) relative = days + i18n.dayShort + (hours > 0 ? hours + i18n.hourShort : '');
      else if (hours > 0) relative = hours + i18n.hourShort;
      else relative = Math.max(1, minutes) + i18n.minuteShort;
      return fmtDate(ms) + ' · ' + i18n.about + relative + i18n.untilExhausted;
    }
    function warn(msg) {
      console.warn('[KimiHistory]', msg);
    }

    function loadScript(src) {
      return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error('Failed to load ' + src));
        document.head.appendChild(s);
      });
    }

    function tryRender() {
      if (!chartReady || !pendingPayload) return;
      render(pendingPayload, pendingIsDark);
      pendingPayload = null;
    }

    function themeColors(isDark) {
      const read = (name, fallback) => {
        const bodyValue = getComputedStyle(document.body).getPropertyValue(name).trim();
        if (bodyValue) return bodyValue;
        const rootValue = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return rootValue || fallback;
      };
      return {
        line: read('--vscode-charts-blue', isDark ? '#7aa2f7' : '#2563eb'),
        fill: isDark ? 'rgba(122,162,247,0.14)' : 'rgba(37,99,235,0.12)',
        forecast: read('--vscode-charts-orange', isDark ? '#f59e0b' : '#c2410c'),
        pace: read('--vscode-charts-red', isDark ? '#f87171' : '#dc2626'),
        axis: read('--vscode-descriptionForeground', isDark ? '#9ca3af' : '#6b7280'),
        grid: isDark ? 'rgba(156,163,175,0.18)' : 'rgba(107,114,128,0.18)',
        tooltipBg: isDark ? 'rgba(30,30,30,0.96)' : 'rgba(255,255,255,0.98)',
        tooltipTitle: isDark ? '#f3f4f6' : '#111827',
        tooltipBody: isDark ? '#d1d5db' : '#374151',
        tooltipBorder: isDark ? 'rgba(255,255,255,0.16)' : 'rgba(0,0,0,0.12)',
      };
    }

    function destroyCharts() {
      charts.forEach((chart) => {
        if (chart) chart.destroy();
      });
      charts.length = 0;
    }

    function render(payload, isDark) {
      if (!payload || !payload.series || payload.series.length === 0 || payload.sampleSize === 0) {
        destroyCharts();
        root.innerHTML = '<div class="empty">' + escapeHtml(i18n.noHistory) + '</div>';
        return;
      }
      destroyCharts();
      const colors = themeColors(isDark);
      const confidenceMap = { high: i18n.high, medium: i18n.medium, low: i18n.low, none: i18n.none };
      const trendMap = { increasing: i18n.increasing, decreasing: i18n.decreasing, stable: i18n.stable };
      const seriesCards = payload.series.map((s, idx) => {
        const p = s.prediction;
        const latest = s.points[s.points.length - 1];
        const conf = confidenceMap[p.confidence] || p.confidence;
        const br = p.burnRatePercent;
        let trendStatus, warn;
        if (br == null) {
          trendStatus = trendMap[p.trend] || i18n.steady;
          warn = false;
        } else if (br >= 120) {
          trendStatus = i18n.burningFast;
          warn = true;
        } else if (br >= 80) {
          trendStatus = i18n.onTrack;
          warn = false;
        } else if (br >= 0) {
          trendStatus = i18n.slowingDown;
          warn = false;
        } else {
          trendStatus = i18n.recovering;
          warn = false;
        }
        const exhaustionText = p.alreadyExhausted
          ? i18n.alreadyExceeded
          : p.predictedExhaustionTs
            ? fmtExhaustion(p.predictedExhaustionTs)
            : s.windowType === 'fiveHours' || s.windowType === 'other'
              ? '—'
              : '∞';
        const usagePercent = p.limit && p.limit > 0 ? Math.round((p.currentUsed ?? 0) / p.limit * 100) + '%' : '—';
        const remainingPercent = latest ? fmtWholePct(latest.percent_left) : '—';
        const tableRows = s.points.slice(-12).reverse().map(point => [
          '<tr>',
            '<td>' + escapeHtml(fmtDate(point.ts)) + '</td>',
            '<td>' + escapeHtml(fmtPct(point.percent_left)) + '</td>',
            '<td>' + escapeHtml(fmtUsage(point.used, point.limit)) + '</td>',
            '<td>' + escapeHtml(fmtPace(point.paceRatio)) + '</td>',
          '</tr>',
        ].join('')).join('');
        return [
          '<section class="card">',
            '<div class="card-header">',
              '<div class="card-title">',
                '<strong>' + escapeHtml(s.label) + '</strong>',
                '<div class="card-meta"><span class="pill">' + s.points.length + ' ' + i18n.snapshots + '</span> · ' + escapeHtml(conf) + ' ' + i18n.confidence + '</div>',
              '</div>',
              '<div class="metric"><span>' + i18n.remainingPercent + '</span><strong>' + remainingPercent + '</strong></div>',
            '</div>',
            '<div class="chart-wrap"><canvas id="c-' + idx + '" role="img" aria-label="' + escapeHtml(s.label + ' ' + i18n.remainingPercent) + '"></canvas></div>',
            '<div class="stats-grid">',
              '<div class="stat' + (warn ? ' warn' : '') + '">',
                '<div class="stat-label">' + i18n.trend + '</div>',
                '<div class="stat-value' + (warn ? ' warn' : '') + '">' + escapeHtml(trendStatus) + '</div>',
              '</div>',
              '<div class="stat">',
                '<div class="stat-label">' + i18n.predictedExhaustion + '</div>',
                '<div class="stat-value">' + escapeHtml(exhaustionText) + '</div>',
              '</div>',
              '<div class="stat">',
                '<div class="stat-label">' + i18n.usage + '</div>',
                '<div class="stat-value">' + usagePercent + '</div>',
              '</div>',
            '</div>',
            '<details>',
              '<summary>' + s.points.length + ' ' + i18n.snapshots + '</summary>',
              '<div class="table-wrap">',
                '<table>',
                  '<thead><tr><th>' + i18n.time + '</th><th>' + i18n.remainingPercent + '</th><th>' + i18n.usage + '</th><th>' + i18n.paceRatio + '</th></tr></thead>',
                  '<tbody>' + tableRows + '</tbody>',
                '</table>',
              '</div>',
            '</details>',
          '</section>',
        ].join('');
      }).join('');

      root.innerHTML = '<div class="history-grid">' + seriesCards + '</div><div class="footer">' + payload.sampleSize + ' ' + i18n.snapshots + ' · ' + payload.retentionDays + i18n.dayShort + '</div>';

      payload.series.forEach((s, idx) => {
        const canvas = document.getElementById('c-' + idx);
        if (!canvas) { warn('canvas c-' + idx + ' not found'); return; }
        if (!window.Chart) { warn('window.Chart missing for c-' + idx); return; }
        try {
          const data = s.points
            .filter(p => isFiniteNumber(p.ts) && isFiniteNumber(p.percent_left))
            .map(p => ({ x: p.ts, y: p.percent_left }));
          const paceData = s.points
            .filter(p => isFiniteNumber(p.ts) && isFiniteNumber(p.paceRatio))
            .map(p => ({ x: p.ts, y: p.paceRatio }));
          const latest = data[data.length - 1];
          const forecastData = [];
          const first = data[0];
          const actualSpan = first && latest ? Math.max(latest.x - first.x, 1) : 1;
          const forecastHorizon = latest && s.prediction?.predictedExhaustionTs
            ? s.prediction.predictedExhaustionTs - latest.x
            : 0;
          const shouldPlotForecast = s.windowType !== 'fiveHours'
            && s.windowType !== 'other'
            && latest
            && forecastHorizon > 0
            && forecastHorizon <= Math.max(actualSpan * 2.5, 6 * 3600 * 1000);
          if (shouldPlotForecast && s.prediction && s.prediction.predictedExhaustionTs) {
            forecastData.push({ x: latest.x, y: latest.y });
            forecastData.push({ x: s.prediction.predictedExhaustionTs, y: 0 });
          }
          const hasPace = paceData.length > 0;
          const datasets = [{
            label: i18n.remainingPercent,
            data,
            borderColor: colors.line,
            borderWidth: 2,
            backgroundColor: colors.fill,
            tension: 0.25,
            cubicInterpolationMode: 'monotone',
            fill: true,
            pointRadius: data.length <= 12 ? 2.5 : 0,
            pointHoverRadius: 4,
            yAxisID: 'y',
          }];
          if (forecastData.length > 0) {
            datasets.push({
              label: i18n.predictedExhaustion,
              data: forecastData,
              borderColor: colors.forecast,
              borderWidth: 1.75,
              backgroundColor: 'transparent',
              borderDash: [6, 4],
              tension: 0,
              fill: false,
              pointRadius: 0,
              pointHoverRadius: 3,
              yAxisID: 'y',
            });
          }
          if (hasPace) {
            datasets.push({
              label: i18n.paceRatio,
              data: paceData,
              borderColor: colors.pace,
              borderWidth: 1.75,
              backgroundColor: 'transparent',
              borderDash: [2, 3],
              tension: 0.2,
              fill: false,
              pointRadius: 0,
              pointHoverRadius: 3,
              yAxisID: 'y1',
            });
          }
          charts[idx] = new Chart(canvas, {
            type: 'line',
            data: { datasets },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              animation: false,
              normalized: true,
              parsing: false,
              interaction: { mode: 'index', intersect: false },
              scales: {
                x: {
                  type: 'linear',
                  grid: { color: colors.grid, drawBorder: false },
                  border: { color: colors.grid },
                  ticks: {
                    color: colors.axis,
                    maxTicksLimit: 5,
                    maxRotation: 0,
                    minRotation: 0,
                    callback: v => fmtAxisTime(Number(v)),
                  },
                  title: { display: true, text: i18n.time, font: { size: 11 }, color: colors.axis },
                },
                y: {
                  beginAtZero: true,
                  max: 100,
                  grid: { color: colors.grid, drawBorder: false },
                  border: { color: colors.grid },
                  title: { display: true, text: i18n.remainingPercent, font: { size: 11 }, color: colors.axis },
                  ticks: { color: colors.axis, callback: v => v + '%' },
                },
                y1: hasPace ? {
                  position: 'right',
                  beginAtZero: true,
                  suggestedMax: 1.5,
                  title: { display: true, text: i18n.paceRatio, font: { size: 11 }, color: colors.axis },
                  grid: { drawOnChartArea: false, color: colors.grid },
                  border: { color: colors.grid },
                  ticks: { color: colors.axis, callback: v => Number(v).toFixed(2) },
                } : undefined,
              },
              plugins: {
                legend: {
                  display: datasets.length > 1,
                  position: 'bottom',
                  align: 'start',
                  labels: {
                    usePointStyle: true,
                    pointStyle: 'line',
                    boxWidth: 24,
                    padding: 14,
                    font: { size: 11 },
                    color: colors.axis,
                  },
                },
                tooltip: {
                  backgroundColor: colors.tooltipBg,
                  titleColor: colors.tooltipTitle,
                  bodyColor: colors.tooltipBody,
                  borderColor: colors.tooltipBorder,
                  borderWidth: 1,
                  cornerRadius: 6,
                  padding: 10,
                  displayColors: true,
                  usePointStyle: true,
                  callbacks: {
                    title: items => items.length ? fmtDate(items[0].parsed.x) : '',
                    label: ctx => {
                      if (ctx.dataset.yAxisID === 'y1') return ctx.dataset.label + ': ' + fmtPace(ctx.parsed.y);
                      return ctx.dataset.label + ': ' + fmtPct(ctx.parsed.y);
                    }
                  }
                },
              },
            },
          });
        } catch (e) {
          warn('chart c-' + idx + ' error: ' + (e && e.message ? e.message : String(e)));
        }
      });
    }

    window.addEventListener('message', (ev) => {
      const msg = ev.data;
      if (msg && msg.type === 'data') {
        pendingPayload = msg.payload;
        pendingIsDark = msg.isDark;
        tryRender();
      }
    });

    (async () => {
      try {
        await loadScript(${scriptUriJson});
        chartReady = true;
      } catch (e) {
        warn('Chart.js load failed: ' + (e && e.message ? e.message : String(e)));
        root.innerHTML = '<div class="empty">' + escapeHtml(i18n.chartLoadFailed) + '</div>';
        return;
      }
      tryRender();
      vscode.postMessage({ type: 'requestData' });
    })();
  </script>
</body>
</html>`;
  }
}

export function buildPayload(snapshots: Snapshot[], retentionDays = DEFAULT_HISTORY_RETENTION_DAYS): Payload {
  const seen: WindowType[] = [];
  for (const s of snapshots) {
    for (const item of s.items) {
      if (!seen.includes(item.windowType)) seen.push(item.windowType);
    }
  }
  const series: Series[] = seen
    .map((wt) => buildSeries(snapshots, wt))
    .filter((s): s is Series => s !== null);

  return {
    generatedAt: Date.now(),
    series,
    sampleSize: snapshots.length,
    retentionDays,
  };
}

function buildSeries(snapshots: Snapshot[], windowType: WindowType): Series | null {
  const points: Series['points'] = [];
  for (const s of snapshots) {
    for (const item of s.items) {
      if (item.windowType !== windowType) continue;
      if (item.limit <= 0) continue;
      points.push({
        ts: s.ts,
        label: item.label,
        percent_left: item.percent_left,
        used: item.used,
        limit: item.limit,
        paceRatio: item.paceRatio,
      });
    }
  }
  if (points.length === 0) return null;
  points.sort((a, b) => a.ts - b.ts);
  const first = points[0]!;
  return {
    windowType,
    label: localizedLimitName(first.label) || first.label,
    points,
    prediction: predictExhaustion(snapshots, windowType),
  };
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    switch (c) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      default:
        return '&#39;';
    }
  });
}
