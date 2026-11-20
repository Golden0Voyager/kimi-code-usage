import * as vscode from 'vscode';
import {
  type ErrorPresentation,
  type PaceState,
  type RedAlertCondition,
  type Snapshot,
  type SnapshotItem,
  type StatusBarAlignmentChoice,
  type ThresholdConfig,
  type UsageItem,
  type WindowType,
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
  fetchMonthlyUsageViaOAuth,
} from './api';
import { fetchUsageCached } from './apiCache';
import {
  resolveApiKey,
  readPaceThresholds,
  readThresholdSettings,
  readPrimaryProvider,
  readProviderSettings,
  enabledProviders,
} from './config';
import { computePace, formatPaceBar, getPacePresentation } from './pace';
import { getProvider } from './providers/registry';
import type { ProviderId } from './providers/types';
import type { SnapshotStore } from './storage';
import type { Notifier } from './notifier';

let statusBarItem: vscode.StatusBarItem | undefined;
let intervalId: NodeJS.Timeout | undefined;
let statusBarCommandId = 'kimiCodeUsage.showDetails';
let snapshotStore: SnapshotStore | undefined;
let notifier: Notifier | undefined;
let refreshInFlight: Promise<void> | undefined;

/** Latest successful fetch per provider, reused by showDetails(). */
const lastProviderItems = new Map<ProviderId, UsageItem[]>();

export function setSnapshotStore(store: SnapshotStore | undefined): void {
  snapshotStore = store;
}

export function setNotifier(n: Notifier | undefined): void {
  notifier = n;
}

/** Test hook: the most recent items per provider. */
export function getLastProviderItems(): Map<ProviderId, UsageItem[]> {
  return lastProviderItems;
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
  clearInterval(intervalId);

  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const configured = cfg.get<number>('refreshIntervalMinutes', 5);
  const safeMinutes = Number.isFinite(configured) ? Math.max(MIN_REFRESH_MINUTES, configured) : 5;
  intervalId = setInterval(refresh, safeMinutes * 60 * 1000);
}

export function stopInterval(): void {
  clearInterval(intervalId);
  intervalId = undefined;
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

/** Fetch a non-primary provider best-effort; failures log and yield []. */
async function fetchSecondaryProvider(id: ProviderId): Promise<UsageItem[]> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const settings = readProviderSettings(cfg, id);
  if (!settings.apiKey) return [];
  try {
    return await getProvider(id).fetch(settings.apiKey, settings.baseUrl);
  } catch (err) {
    console.warn(`[KimiCodeUsage] provider ${id} fetch failed: ${String(err)}`);
    return [];
  }
}

async function refreshOnce(): Promise<void> {
  if (!statusBarItem) return;
  const item = statusBarItem;

  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const primary = readPrimaryProvider(cfg);
  const providerIds = enabledProviders(cfg);

  // Secondary providers never block the status bar; collect for the tooltip.
  const secondary: Array<{ id: ProviderId; items: UsageItem[] }> = [];
  for (const id of providerIds) {
    if (id === primary) continue;
    const items = await fetchSecondaryProvider(id);
    if (items.length > 0) secondary.push({ id, items });
    if (items.length > 0) lastProviderItems.set(id, items);
  }

  if (primary === 'kimi') {
    await refreshKimi(item, cfg, secondary);
    return;
  }

  await refreshNonKimiPrimary(item, cfg, primary, secondary);
}

async function refreshKimi(
  item: vscode.StatusBarItem,
  cfg: vscode.WorkspaceConfiguration,
  secondary: Array<{ id: ProviderId; items: UsageItem[] }>,
): Promise<void> {
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
    const { payload: data } = await fetchUsageCached('kimi', baseUrl, apiKey);
    const items = parsePayload(data);

    if (items.length === 0) {
      item.text = `$(chip) ${t('Kimi: --')}`;
      item.tooltip = t('No usage data');
      item.backgroundColor = undefined;
      console.warn('[KimiCodeUsage] API returned empty usage items. Payload structure may have changed.');
      return;
    }

    try {
      const monthly = await fetchMonthlyUsageViaOAuth(baseUrl);
      if (monthly) items.push(monthly);
    } catch {
      // OAuth monthly is best-effort; never block the main display
    }

    lastProviderItems.set('kimi', items);

    const weeklyItem = findWindowItem(items, 'weekly');
    const fiveHoursItem = findWindowItem(items, 'fiveHours');

    const showPace = cfg.get<boolean>('showPaceIndicator', true);
    const showPaceBar = cfg.get<boolean>('showPaceBar', true);

    let pace: PaceState | null = null;
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

    const compactTypes: WindowType[] = ['weekly', 'fiveHours', 'monthly'];
    const parts = items
      .filter((i) => compactTypes.includes(detectWindowType(i.label)))
      .map((i) => `${shortLabel(i.label)}:${i.percent_left.toFixed(0)}%`);
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

    const overviewEntries = items.map((i) =>
      i.text_value != null
        ? `${localizedLimitName(i.label)}: ${i.text_value}`
        : `${localizedLimitName(i.label)}: ${i.percent_left.toFixed(0)}% ${t('left')}`,
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
        if (detectWindowType(i.label) === 'other') continue;
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
    pushSecondarySections(markdownLines, secondary);

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

function pushSecondarySections(
  lines: string[],
  secondary: Array<{ id: ProviderId; items: UsageItem[] }>,
): void {
  for (const { id, items } of secondary) {
    const displayName = getProvider(id).spec.displayName;
    const entries = items.map((i) =>
      i.text_value != null
        ? `${i.label}: ${i.text_value}`
        : `${i.label}: ${i.percent_left.toFixed(0)}% ${t('left')}`,
    );
    pushSection(lines, displayName, entries);
  }
}

/** Compact money summary for a non-window provider: `$X left` or `$X used`. */
function compactMoneySummary(items: UsageItem[]): string | null {
  const first = items.find((i) => i.label === 'Credits' || i.label === 'Key Usage' || i.label === 'Cost');
  if (!first) return null;
  if (first.limit > 0) return `$${first.remaining.toFixed(2)} left`;
  return `$${first.used.toFixed(2)} used`;
}

/** Compact status-bar text for a non-window primary provider. Exported for tests. */
export function nonKimiStatusText(spec: { displayName: string }, items: UsageItem[]): string {
  if (items.length === 0) return `$(chip) ${spec.displayName}: --`;
  const summary = compactMoneySummary(items);
  return summary !== null ? `$(cloud) ${spec.displayName}: ${summary}` : `$(cloud) ${spec.displayName}: --`;
}

async function refreshNonKimiPrimary(
  item: vscode.StatusBarItem,
  cfg: vscode.WorkspaceConfiguration,
  primary: ProviderId,
  secondary: Array<{ id: ProviderId; items: UsageItem[] }>,
): Promise<void> {
  const settings = readProviderSettings(cfg, primary);
  const spec = getProvider(primary).spec;

  if (!settings.apiKey) {
    item.text = `$(key) ${t('API Key Missing')}`;
    item.tooltip = t('Set the API key via "Kimi Code Usage: Configure Providers".');
    item.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    return;
  }

  try {
    const items = await getProvider(primary).fetch(settings.apiKey, settings.baseUrl);

    lastProviderItems.set(primary, items);
    item.text = nonKimiStatusText(spec, items);

    const markdownLines: string[] = [];
    const entries = items.map((i) =>
      i.text_value != null
        ? `${i.label}: ${i.text_value}`
        : `${i.label}: ${i.percent_left.toFixed(0)}% ${t('left')}`,
    );
    pushSection(markdownLines, spec.displayName, entries);
    pushSecondarySections(markdownLines, secondary);

    const tooltip = new vscode.MarkdownString(markdownLines.join('\n'));
    tooltip.supportThemeIcons = true;
    item.tooltip = tooltip;
    item.backgroundColor = undefined;
  } catch (err) {
    const errorView = buildErrorPresentation(err);
    item.text = errorView.text;
    item.tooltip = errorView.tooltip;
    item.backgroundColor = errorView.isWarning
      ? new vscode.ThemeColor('statusBarItem.errorBackground')
      : undefined;
  }
}

function providerPickItems(
  id: ProviderId,
  items: UsageItem[],
  showPace: boolean,
  paceThresholds: ThresholdConfig,
  cfg: vscode.WorkspaceConfiguration,
): vscode.QuickPickItem[] {
  return items.map((qi) => {
    const label =
      qi.text_value != null
        ? `${qi.label}: ${qi.text_value}`
        : `${qi.label}: ${qi.percent_left.toFixed(0)}% ${t('left')}`;
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
}

export async function showDetails(): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const primary = readPrimaryProvider(cfg);
  const providerIds = enabledProviders(cfg);

  if (providerIds.length === 0) {
    vscode.window.showWarningMessage(t('No usage data'));
    return;
  }

  try {
    const paceThresholds = readPaceThresholds(cfg);
    const showPace = cfg.get<boolean>('showPaceIndicator', true);

    const perProvider: Array<{ id: ProviderId; items: UsageItem[] }> = [];
    for (const id of providerIds) {
      const settings = readProviderSettings(cfg, id);
      const baseUrl =
        id === 'kimi' ? cfg.get<string>('baseUrl', 'https://api.kimi.com/coding/v1') : settings.baseUrl;
      if (typeof baseUrl !== 'string' || baseUrl.trim().length === 0) {
        vscode.window.showWarningMessage(
          `${t('Can you hear me, Major Kimi?')}\n${t('Check baseUrl and network link.')}`,
        );
        return;
      }
      const key = id === 'kimi' ? await resolveApiKey() : settings.apiKey;
      if (key.length === 0) {
        if (id === primary) {
          vscode.window.showWarningMessage(
            `${t('Can you hear me, Major Kimi?')}\n${t('Set `kimiCodeUsage.apiKey` or `.env` key to reconnect.')}`,
          );
          return;
        }
        continue;
      }
      let items = lastProviderItems.get(id) ?? [];
      if (items.length === 0 && id === primary) {
        const fetched =
          id === 'kimi'
            ? parsePayload((await fetchUsageCached('kimi', baseUrl, key)).payload)
            : await getProvider(id).fetch(key, baseUrl);
        items = fetched;
        lastProviderItems.set(id, fetched);
      }
      if (items.length === 0) continue;
      perProvider.push({ id, items });
    }

    const picks: vscode.QuickPickItem[] = [];
    for (const { id, items } of perProvider) {
      if (perProvider.length > 1) {
        picks.push({
          label: getProvider(id).spec.displayName,
          kind: vscode.QuickPickItemKind.Separator,
        });
      }
      picks.push(...providerPickItems(id, items, showPace, paceThresholds, cfg));
    }

    if (picks.length === 0) {
      vscode.window.showInformationMessage(t('No usage data'));
      return;
    }

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
