import * as vscode from 'vscode';
import {
  type ErrorPresentation,
  type RedAlertCondition,
  type StatusBarAlignmentChoice,
  type Snapshot,
  type SnapshotItem,
  type UsageItem,
  MIN_REFRESH_MINUTES,
} from './types';
import { t } from './i18n';
import {
  parsePayload,
  isLinkIssue,
  findWindowItem,
  isLowRemaining,
  localizedLimitName,
  shortLabel,
  getWindowSeconds,
  formatResetTimeAbsolute,
  detectWindowType,
} from './api';
import { fetchUsageCached } from './apiCache';
import { resolveApiKey, readPaceThresholds, readThresholdSettings } from './config';
import { computePace, formatPaceBar, getPacePresentation } from './pace';
import type { SnapshotStore } from './storage';
import type { Notifier } from './notifier';

let statusBarItem: vscode.StatusBarItem | undefined;
let intervalId: NodeJS.Timeout | undefined;
let statusBarCommandId = 'kimiCodeUsage.showDetails';
let snapshotStore: SnapshotStore | undefined;
let notifier: Notifier | undefined;
let refreshInFlight: Promise<void> | undefined;

export function setSnapshotStore(store: SnapshotStore | undefined): void {
  snapshotStore = store;
}

export function setNotifier(n: Notifier | undefined): void {
  notifier = n;
}

function buildErrorPresentation(err: unknown): ErrorPresentation {
  const raw = String(err ?? '');
  const lower = raw.toLowerCase();

  if (lower.includes('timeout')) {
    return {
      text: `\uD83C\uDF11  ${t('Can you hear me, Major Kimi?')}`,
      tooltip: `${t("Ground Control to Major Kimi \u2014 Planet Earth is blue and there's nothing I can do.")}\n${t('Check baseUrl and network link.')}`,
      isWarning: false,
    };
  }

  if (lower.includes('http 401') || lower.includes('http 403')) {
    return {
      text: `$(lock) ${t('Auth Failed Short')}`,
      tooltip: `${t('Authentication failed. Please check API key and permissions.')}: ${raw}`,
      isWarning: true,
    };
  }

  if (lower.includes('http 429')) {
    return {
      text: `$(warning) ${t('Rate Limited Short')}`,
      tooltip: `${t('Rate limit exceeded. Please wait and retry.')}: ${raw}`,
      isWarning: true,
    };
  }

  if (lower.includes('http 5')) {
    return {
      text: `$(server-process) ${t('Server Error Short')}`,
      tooltip: `${t('Server error from Kimi API. Please retry shortly.')}: ${raw.slice(0, 200)}`,
      isWarning: false,
    };
  }

  if (isLinkIssue(err)) {
    return {
      text: `\uD83C\uDF11  ${t('Can you hear me, Major Kimi?')}`,
      tooltip: `${t("Ground Control to Major Kimi \u2014 Planet Earth is blue and there's nothing I can do.")}\n${t('Check baseUrl and network link.')}`,
      isWarning: false,
    };
  }

  return {
    text: `$(error) ${t('Request Failed Short')}`,
    tooltip: `${t('Request Failed Short')}: ${raw.slice(0, 200)}`,
    isWarning: false,
  };
}

function pushSection(lines: string[], title: string, entries: string[]) {
  if (entries.length === 0) return;
  if (lines.length > 0) lines.push('');
  lines.push(`**${title}**`);
  for (const entry of entries) lines.push(`- ${entry}`);
}

export function createStatusBarItem(): vscode.StatusBarItem {
  if (statusBarItem) {
    statusBarItem.dispose();
  }
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const alignment = cfg.get<StatusBarAlignmentChoice>('statusBarAlignment', 'Right');
  statusBarItem = vscode.window.createStatusBarItem(
    alignment === 'Left' ? vscode.StatusBarAlignment.Left : vscode.StatusBarAlignment.Right,
    100,
  );
  statusBarItem.command = statusBarCommandId;
  statusBarItem.show();
  return statusBarItem;
}

export function setStatusBarCommand(commandId: string): void {
  statusBarCommandId = commandId;
  if (statusBarItem) statusBarItem.command = commandId;
}

export function restartInterval(): void {
  if (intervalId) clearInterval(intervalId);

  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const configured = cfg.get<number>('refreshIntervalMinutes', 5);
  const safeMinutes = Number.isFinite(configured) ? Math.max(MIN_REFRESH_MINUTES, configured) : 5;
  intervalId = setInterval(refresh, safeMinutes * 60 * 1000);
}

export function stopInterval(): void {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = undefined;
  }
}

export function getStatusBarItem(): vscode.StatusBarItem | undefined {
  return statusBarItem;
}

export function refresh(): Promise<void> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = refreshOnce().finally(() => {
    refreshInFlight = undefined;
  });
  return refreshInFlight;
}

async function refreshOnce(): Promise<void> {
  if (!statusBarItem) return;
  const item = statusBarItem;

  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const apiKey = await resolveApiKey();
  const baseUrl = cfg.get<string>('baseUrl', 'https://api.kimi.com/coding/v1');
  const thresholds = readThresholdSettings(cfg);
  const paceThresholds = readPaceThresholds(cfg);

  if (!apiKey) {
    item.text = `$(key) ${t('API Key Missing')}`;
    const missingKeyTooltip = new vscode.MarkdownString(
      [
        `**${t("Ground Control to Major Kimi \u2014 Planet Earth is blue and there's nothing I can do.")}**`,
        `${t('Set `kimiCodeUsage.apiKey` or `.env` key to reconnect.')}`,
      ].join('\n'),
    );
    missingKeyTooltip.isTrusted = false;
    item.tooltip = missingKeyTooltip;
    item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    return;
  }

  if (!baseUrl || !baseUrl.trim()) {
    item.text = `\uD83C\uDF11  ${t('Can you hear me, Major Kimi?')}`;
    item.tooltip = `${t("Ground Control to Major Kimi \u2014 Planet Earth is blue and there's nothing I can do.")}\n${t('Check baseUrl and network link.')}`;
    item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    return;
  }

  try {
    const { payload: data } = await fetchUsageCached(baseUrl, apiKey);
    const items = parsePayload(data);

    if (items.length === 0) {
      item.text = `$(chip) ${t('Kimi: --')}`;
      item.tooltip = t('No usage data');
      item.backgroundColor = undefined;
      console.warn('[KimiCodeUsage] API returned empty usage items. Payload structure may have changed.');
      return;
    }

    const weeklyItem = findWindowItem(items, 'weekly');
    const fiveHoursItem = findWindowItem(items, 'fiveHours');

    const showPace = cfg.get<boolean>('showPaceIndicator', true);
    const showPaceBar = cfg.get<boolean>('showPaceBar', true);

    let pace: ReturnType<typeof computePace> = null;
    if (weeklyItem && showPace) {
      pace = computePace(weeklyItem, getWindowSeconds(weeklyItem.label), paceThresholds);
    }
    const paceState = pace?.state || 'normal';
    const pacePresentation = getPacePresentation(cfg, paceState);

    const moonEmoji = (() => {
      const quotaItems = [weeklyItem, fiveHoursItem].filter(Boolean) as UsageItem[];
      for (const qi of quotaItems) {
        if (qi.percent_left >= 99) return '\uD83C\uDF15';
        if (qi.percent_left <= 1) return '\uD83C\uDF11';
      }
      return paceState === 'fast' ? '\uD83C\uDF12' : paceState === 'normal' ? '\uD83C\uDF13' : '\uD83C\uDF14';
    })();

    let paceBarStr = '';
    if (showPaceBar) {
      paceBarStr = pace ? formatPaceBar(pace.ratio, paceThresholds) : '\u25B0\u25B0\u25B1';
    }

    const suffix = showPace ? `> $(${pacePresentation.icon}) ${pacePresentation.label}` : '';

    const parts = items.map((i) => `${shortLabel(i.label)}:${i.percent_left.toFixed(0)}%`);
    const prefix = paceBarStr
      ? `${moonEmoji}  ${paceBarStr}  ${parts.join(' ')}`.trim()
      : `${moonEmoji}  ${parts.join(' ')}`.trim();
    item.text = `${prefix} ${suffix}`.trim();

    const redAlertCondition = cfg.get<RedAlertCondition>('redAlertCondition', 'Either');
    const lowWeekly = isLowRemaining(weeklyItem, thresholds.weekly);
    const lowFiveHours = isLowRemaining(fiveHoursItem, thresholds.fiveHours);
    const thresholdRed =
      redAlertCondition === 'Weekly'
        ? lowWeekly
        : redAlertCondition === '5 Hours'
          ? lowFiveHours
          : lowWeekly || lowFiveHours;
    const shouldRed = pace?.state === 'fast' || thresholdRed;

    item.backgroundColor = shouldRed ? new vscode.ThemeColor('statusBarItem.errorBackground') : undefined;

    const overviewEntries = items.map(
      (i) => `${localizedLimitName(i.label)}: ${i.percent_left.toFixed(0)}% ${t('left')}`,
    );

    if (snapshotStore) {
      const snapItems: SnapshotItem[] = items.map((i) => {
        const itemPace = computePace(i, getWindowSeconds(i.label), paceThresholds);
        return {
          label: i.label,
          windowType: detectWindowType(i.label),
          used: i.used,
          limit: i.limit,
          percent_left: i.percent_left,
          paceRatio: itemPace ? Number(itemPace.ratio.toFixed(4)) : null,
        };
      });
      const snapshot: Snapshot = { ts: Date.now(), items: snapItems };
      void snapshotStore.append(snapshot);
    }

    const resetEntries: string[] = [];
    for (const i of items) {
      const name = localizedLimitName(i.label);
      if (i.reset_at) {
        const formatted = formatResetTimeAbsolute(i.reset_at);
        resetEntries.push(t('{0}: Fuel: {1} | Refuel: {2}', name, formatted.relative, formatted.absolute));
      } else if (i.reset_hint) {
        resetEntries.push(`${name}: ${i.reset_hint}`);
      }
    }

    const paceEntries: string[] = [];
    if (showPace) {
      for (const i of items) {
        const itemPace = computePace(i, getWindowSeconds(i.label), paceThresholds);
        if (!itemPace) continue;
        const itemPacePresentation = getPacePresentation(cfg, itemPace.state);
        const rawDeviation = (itemPace.ratio - 1.0) * 100;
        const deviation = rawDeviation.toFixed(2);
        const sign = rawDeviation > 0 ? '+' : '';
        paceEntries.push(
          `${localizedLimitName(i.label)}: ${sign}${deviation}% ($(${itemPacePresentation.icon}) ${itemPacePresentation.label})`,
        );
      }
    }

    const markdownLines: string[] = [];
    pushSection(markdownLines, t('Usage Telemetry'), overviewEntries);
    pushSection(markdownLines, t('Pace Details'), paceEntries);
    pushSection(markdownLines, t('Reset Schedule'), resetEntries);

    const tooltip = new vscode.MarkdownString(markdownLines.join('\n'));
    tooltip.supportThemeIcons = true;
    item.tooltip = tooltip;

    if (notifier) {
      void notifier.checkAndNotify(items, paceState === 'fast');
    }
  } catch (err) {
    const errorView = buildErrorPresentation(err);
    item.text = errorView.text;
    item.tooltip = errorView.tooltip;
    item.backgroundColor = errorView.isWarning
      ? new vscode.ThemeColor('statusBarItem.errorBackground')
      : undefined;
  }
}

export async function showDetails(): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const apiKey = await resolveApiKey();
  const baseUrl = cfg.get<string>('baseUrl', 'https://api.kimi.com/coding/v1');

  if (!apiKey) {
    vscode.window.showWarningMessage(
      `${t('Can you hear me, Major Kimi?')}\n${t('Set `kimiCodeUsage.apiKey` or `.env` key to reconnect.')}`,
    );
    return;
  }

  if (!baseUrl || !baseUrl.trim()) {
    vscode.window.showWarningMessage(
      `${t('Can you hear me, Major Kimi?')}\n${t('Check baseUrl and network link.')}`,
    );
    return;
  }

  try {
    const { payload: data } = await fetchUsageCached(baseUrl, apiKey);
    const items = parsePayload(data);
    const paceThresholds = readPaceThresholds(cfg);
    const showPace = cfg.get<boolean>('showPaceIndicator', true);

    const picks: vscode.QuickPickItem[] = items.map((qi) => {
      const displayName = localizedLimitName(qi.label);
      const label = `${displayName}: ${qi.percent_left.toFixed(0)}% ${t('left')}`;
      const segments: string[] = [];
      let detail = '';

      if (showPace) {
        const pace = computePace(qi, getWindowSeconds(qi.label), paceThresholds);
        if (pace) {
          const rawDeviation = (pace.ratio - 1.0) * 100;
          const deviation = rawDeviation.toFixed(2);
          const sign = rawDeviation > 0 ? '+' : '';
          const pacePresentation = getPacePresentation(cfg, pace.state);
          segments.push(`${t('Current Pace')}: ${sign}${deviation}%`);
          segments.push(`$(${pacePresentation.icon}) ${pacePresentation.label}`);
        }
      }

      if (qi.reset_at) {
        const formatted = formatResetTimeAbsolute(qi.reset_at);
        detail = t('Resets {0} (in {1})', formatted.absolute, formatted.relative);
      } else if (qi.reset_hint) {
        detail = qi.reset_hint;
      }

      return { label, description: segments.join('  \u2022  '), detail };
    });

    const quickPick = vscode.window.createQuickPick();
    quickPick.items = picks;
    quickPick.placeholder = t('Kimi API Usage Details');
    quickPick.matchOnDescription = true;
    quickPick.matchOnDetail = true;

    const settingsButton: vscode.QuickInputButton = {
      iconPath: new vscode.ThemeIcon('gear'),
      tooltip: t('Open Settings'),
    };
    const supportButton: vscode.QuickInputButton = {
      iconPath: new vscode.ThemeIcon('coffee'),
      tooltip: t('Buy me a coffee'),
    };
    const historyButton: vscode.QuickInputButton = {
      iconPath: new vscode.ThemeIcon('graph'),
      tooltip: t('View Usage History'),
    };
    quickPick.buttons = [supportButton, historyButton, settingsButton];

    quickPick.onDidTriggerButton((button) => {
      if (button.tooltip === settingsButton.tooltip) {
        vscode.commands.executeCommand('workbench.action.openSettings', 'kimiCodeUsage');
        quickPick.hide();
        return;
      }
      if (button.tooltip === supportButton.tooltip) {
        const supportUrl = cfg.get<string>('supportUrl', 'https://ko-fi.com/golden_voyager');
        if (supportUrl && supportUrl.trim()) {
          void vscode.env.openExternal(vscode.Uri.parse(supportUrl));
        }
        quickPick.hide();
        return;
      }
      if (button.tooltip === historyButton.tooltip) {
        void vscode.commands.executeCommand('kimiCodeUsage.showHistory');
        quickPick.hide();
      }
    });

    quickPick.onDidAccept(() => {
      quickPick.hide();
    });

    quickPick.show();
  } catch (err) {
    if (isLinkIssue(err)) {
      vscode.window.showWarningMessage(
        `${t('Can you hear me, Major Kimi?')}\n${t('Check baseUrl and network link.')}`,
      );
      return;
    }
    const raw = String(err ?? '').toLowerCase();
    if (raw.includes('http 5')) {
      vscode.window.showWarningMessage(
        `${t('Server error from Kimi API. Please retry shortly.')}: ${String(err).slice(0, 200)}`,
      );
      return;
    }
    vscode.window.showWarningMessage(`${t('Usage fetch failed')}: ${String(err ?? '').slice(0, 200)}`);
  }
}
