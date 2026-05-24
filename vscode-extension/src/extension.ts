import * as vscode from 'vscode';
import * as https from 'https';
import * as fs from 'fs';
import * as path from 'path';

interface UsageItem {
  label: string;
  used: number;
  limit: number;
  remaining: number;
  percent_left: number;
  reset_hint: string | null;
  reset_seconds: number | null;
  reset_at: string | null;
}

interface PaceState {
  ratio: number;
  state: 'fast' | 'normal' | 'slow';
}

interface PacePresentation {
  label: string;
  icon: string;
}

interface ThresholdSettings {
  weekly: number;
  fiveHours: number;
}

interface ErrorPresentation {
  text: string;
  tooltip: string;
  isWarning: boolean;
}

const WEEKLY_WINDOW_SECONDS = 7 * 24 * 3600;
const MIN_REFRESH_MINUTES = 1;
const DEFAULT_LOW_THRESHOLD = 30;
const ICON_NAME_PATTERN = /^[a-z][a-z0-9-]*$/;

type LanguageChoice = 'Auto' | 'English' | 'Chinese' | 'Japanese' | 'French' | 'German' | 'Spanish' | 'Korean' | 'Russian' | 'Portuguese' | 'Italian';
type WindowType = 'weekly' | 'fiveHours' | 'monthly' | 'other';

type PaceTheme = 'Simple' | 'Animals' | 'Fish' | 'Birds' | 'Racing' | 'Running' | 'F1' | 'Rocket' | 'Star Wars' | 'Star Trek' | 'Back To The Future' | 'Pink Floyd' | 'Submarine' | 'Airliner' | 'Fighter' | 'Firearms';
type PaceSensitivity = 'Relaxed' | 'Normal' | 'Strict' | 'custom';

interface ThresholdConfig {
  fast: number;
  slow: number;
}

const THEME_LABELS: Record<PaceTheme, Record<'fast' | 'normal' | 'slow', string>> = {
  'Simple': { fast: 'Fast', normal: 'Normal', slow: 'Slow' },
  'Animals': { fast: 'Cheetah', normal: 'Lynx', slow: 'Sloth' },
  'Fish': { fast: 'Marlin', normal: 'Dolphin', slow: 'Turtle' },
  'Birds': { fast: 'Peregrine', normal: 'Eagle', slow: 'Ostrich' },
  'Racing': { fast: 'Nitro', normal: 'Cruise', slow: 'Idle' },
  'Running': { fast: 'Sprint', normal: 'Jog', slow: 'Walk' },
  'F1': { fast: 'Overtake Mode', normal: 'Race Pace', slow: 'Safety Car' },
  'Rocket': { fast: 'Thrust', normal: 'Propulsion', slow: 'Hover' },
  'Star Wars': { fast: 'Falcon', normal: 'X-Wing', slow: 'Shuttle' },
  'Star Trek': { fast: 'Defiant', normal: 'Enterprise', slow: 'Voyager' },
  'Back To The Future': { fast: 'Flux', normal: 'Driving', slow: 'Parked' },
  'Pink Floyd': { fast: 'Eclipse', normal: 'Time', slow: 'Breathe' },
  'Submarine': { fast: 'Alfa', normal: 'Ohio', slow: 'U-Boat' },
  'Airliner': { fast: 'Concorde', normal: 'A350', slow: 'Comet' },
  'Fighter': { fast: 'SR-71', normal: 'F-22', slow: 'A-10' },
  'Firearms': { fast: 'Minigun', normal: 'AK-47', slow: 'Revolver' },
};

const SENSITIVITY_THRESHOLDS: Record<Exclude<PaceSensitivity, 'custom'>, ThresholdConfig> = {
  Relaxed: { fast: 1.2, slow: 0.8 },
  Normal: { fast: 1.12, slow: 0.88 },
  Strict: { fast: 1.05, slow: 0.95 },
};

const PACE_CONFIG = {
  fast: {
    labelKey: 'Fast',
    labelSetting: 'paceLabels.fast',
    iconSetting: 'paceIcons.fast',
    defaultIcon: 'warning',
  },
  normal: {
    labelKey: 'Normal',
    labelSetting: 'paceLabels.normal',
    iconSetting: 'paceIcons.normal',
    defaultIcon: 'dashboard',
  },
  slow: {
    labelKey: 'Slow',
    labelSetting: 'paceLabels.slow',
    iconSetting: 'paceIcons.slow',
    defaultIcon: 'coffee',
  },
} as const;

function computePace(item: UsageItem, windowSeconds: number, thresholds: ThresholdConfig): PaceState | null {
  if (!item.reset_seconds || item.reset_seconds <= 0) return null;
  if (item.limit <= 0) return null;

  const elapsed = windowSeconds - item.reset_seconds;
  if (elapsed <= 0 || elapsed < 3600) return null;

  const actualUsedRatio = item.used / item.limit;
  const elapsedRatio = elapsed / windowSeconds;

  const rawRatio = elapsedRatio > 0 ? actualUsedRatio / elapsedRatio : 0;
  const ratio = Math.min(rawRatio, 5.0);

  let state: 'fast' | 'normal' | 'slow';
  if (ratio >= thresholds.fast) state = 'fast';
  else if (ratio <= thresholds.slow) state = 'slow';
  else state = 'normal';

  return { ratio, state };
}

function detectWindowType(label: string): WindowType {
  const lower = label.toLowerCase();
  if (lower.includes('weekly') || lower.includes('week') || lower.includes('周')) return 'weekly';
  if (lower.includes('5h') || lower.includes('5 hour') || lower.includes('5小时')) return 'fiveHours';
  if (lower.includes('month') || lower.includes('monthly') || lower.includes('月')) return 'monthly';
  return 'other';
}

function getWindowSeconds(label: string): number {
  const windowType = detectWindowType(label);
  if (windowType === 'fiveHours') return 5 * 3600;
  if (windowType === 'monthly') return 30 * 24 * 3600;
  return WEEKLY_WINDOW_SECONDS;
}

function formatPaceBar(ratio: number, thresholds: ThresholdConfig): string {
  let filled: number;
  if (ratio >= thresholds.fast) filled = 3;
  else if (ratio >= thresholds.slow) filled = 2;
  else filled = 1;
  return '▰'.repeat(filled) + '▱'.repeat(3 - filled);
}

let statusBarItem: vscode.StatusBarItem;
let intervalId: NodeJS.Timeout | undefined;
let translator: Translator;

class Translator {
  private bundles = new Map<string, Record<string, string>>();
  private currentLang = 'en';
  private languageChoice: LanguageChoice = 'Auto';

  constructor(context: vscode.ExtensionContext) {
    this.loadAll(context);
    this.update(context);
  }

  private loadAll(context: vscode.ExtensionContext) {
    const langs = ['en', 'zh-cn', 'ja', 'fr', 'de', 'es', 'ko', 'ru', 'pt', 'it'];
    for (const lang of langs) {
      const filePath = path.join(context.extensionPath, 'l10n', `bundle.l10n.${lang}.json`);
      try {
        if (fs.existsSync(filePath)) {
          const content = JSON.parse(fs.readFileSync(filePath, 'utf8'));
          this.bundles.set(lang, content);
        }
      } catch (e) {
        console.error(`Failed to load l10n bundle for ${lang}`, e);
      }
    }
  }

  update(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('kimiCodeUsage');
    const lang = config.get<LanguageChoice>('language', 'Auto');
    this.languageChoice = lang;

    if (lang === 'Auto') {
      this.currentLang = this.mapEnvLanguage(vscode.env.language.toLowerCase());
    } else {
      const map: Record<Exclude<LanguageChoice, 'Auto'>, string> = {
        'English': 'en',
        'Chinese': 'zh-cn',
        'Japanese': 'ja',
        'French': 'fr',
        'German': 'de',
        'Spanish': 'es',
        'Korean': 'ko',
        'Russian': 'ru',
        'Portuguese': 'pt',
        'Italian': 'it',
      };
      this.currentLang = map[lang] ?? 'en';
    }
  }

  private mapEnvLanguage(envLang: string): string {
    if (envLang.startsWith('zh')) return 'zh-cn';
    if (envLang.startsWith('ja')) return 'ja';
    if (envLang.startsWith('fr')) return 'fr';
    if (envLang.startsWith('de')) return 'de';
    if (envLang.startsWith('es')) return 'es';
    if (envLang.startsWith('ko')) return 'ko';
    if (envLang.startsWith('ru')) return 'ru';
    if (envLang.startsWith('pt')) return 'pt';
    if (envLang.startsWith('it')) return 'it';
    return 'en';
  }

  t(message: string, ...args: unknown[]): string {
    const bundle = this.bundles.get(this.currentLang) ?? this.bundles.get('en');
    let str = bundle?.[message] ?? vscode.l10n.t(message);

    if (args.length > 0) {
      args.forEach((arg, i) => {
        str = str.replace(`{${i}}`, String(arg));
      });
    }
    return str;
  }

  lang(): string {
    return this.currentLang;
  }

  isZh(): boolean {
    return this.currentLang === 'zh-cn';
  }
}

function createStatusBarItem() {
  if (statusBarItem) {
    statusBarItem.dispose();
  }
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const alignment = cfg.get<'Left' | 'Right'>('statusBarAlignment', 'Right');
  statusBarItem = vscode.window.createStatusBarItem(
    alignment === 'Left' ? vscode.StatusBarAlignment.Left : vscode.StatusBarAlignment.Right,
    100
  );
  statusBarItem.command = 'kimiCodeUsage.showDetails';
  statusBarItem.show();
}

export function activate(context: vscode.ExtensionContext) {
  translator = new Translator(context);

  createStatusBarItem();

  const refreshCmd = vscode.commands.registerCommand('kimiCodeUsage.refresh', refresh);
  const detailsCmd = vscode.commands.registerCommand('kimiCodeUsage.showDetails', showDetails);

  const configChangeDisposable = vscode.workspace.onDidChangeConfiguration(async (e) => {
    if (!e.affectsConfiguration('kimiCodeUsage')) return;

    const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');

    if (e.affectsConfiguration('kimiCodeUsage.language')) {
      translator.update(context);
    }

    if (e.affectsConfiguration('kimiCodeUsage.statusBarAlignment')) {
      createStatusBarItem();
    }

    // Sensitivity changed -> auto-sync thresholds
    if (e.affectsConfiguration('kimiCodeUsage.paceSensitivity')) {
      const sensitivity = cfg.get<PaceSensitivity>('paceSensitivity', 'Normal');
      if (sensitivity !== 'custom') {
        const preset = SENSITIVITY_THRESHOLDS[sensitivity] ?? SENSITIVITY_THRESHOLDS.Normal;
        await cfg.update('paceThresholdFast', preset.fast, true);
        await cfg.update('paceThresholdSlow', preset.slow, true);
      }
    }

    // Thresholds changed -> auto-detect sensitivity match
    const fastChanged = e.affectsConfiguration('kimiCodeUsage.paceThresholdFast');
    const slowChanged = e.affectsConfiguration('kimiCodeUsage.paceThresholdSlow');
    const sensitivityChanged = e.affectsConfiguration('kimiCodeUsage.paceSensitivity');
    // Skip if only one threshold changed (partial update from sensitivity sync)
    if ((fastChanged && slowChanged) && !sensitivityChanged) {
      const fast = cfg.get<number>('paceThresholdFast');
      const slow = cfg.get<number>('paceThresholdSlow');
      if (Number.isFinite(fast) && Number.isFinite(slow)) {
        let matched: PaceSensitivity | null = null;
        for (const [key, preset] of Object.entries(SENSITIVITY_THRESHOLDS)) {
          if (key === 'custom') continue;
          if (preset.fast === fast && preset.slow === slow) {
            matched = key as PaceSensitivity;
            break;
          }
        }
        await cfg.update('paceSensitivity', matched ?? 'custom', true);
      }
    }

    restartInterval();
    refresh();
  });

  context.subscriptions.push(statusBarItem, refreshCmd, detailsCmd, configChangeDisposable);

  refresh();
  restartInterval();
}

function t(message: string, ...args: unknown[]): string {
  return translator.t(message, ...args);
}

function sanitizePercentThreshold(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  const numeric = value as number;
  return Math.max(0, Math.min(100, numeric));
}

function readThresholdSettings(cfg: vscode.WorkspaceConfiguration): ThresholdSettings {
  return {
    weekly: sanitizePercentThreshold(cfg.get<number>('weeklyLowThresholdPercent', DEFAULT_LOW_THRESHOLD), DEFAULT_LOW_THRESHOLD),
    fiveHours: sanitizePercentThreshold(cfg.get<number>('fiveHourLowThresholdPercent', DEFAULT_LOW_THRESHOLD), DEFAULT_LOW_THRESHOLD),
  };
}

function readPaceThresholds(cfg: vscode.WorkspaceConfiguration): ThresholdConfig {
  const sensitivity = cfg.get<PaceSensitivity>('paceSensitivity', 'Normal');
  const preset = sensitivity === 'custom'
    ? SENSITIVITY_THRESHOLDS.Normal
    : (SENSITIVITY_THRESHOLDS[sensitivity] ?? SENSITIVITY_THRESHOLDS.Normal);

  const customFast = cfg.get<number>('paceThresholdFast');
  const customSlow = cfg.get<number>('paceThresholdSlow');

  return {
    fast: Number.isFinite(customFast) ? customFast! : preset.fast,
    slow: Number.isFinite(customSlow) ? customSlow! : preset.slow,
  };
}

function normalizeIconName(raw: string, fallback: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return fallback;

  let name = trimmed;
  if (name.startsWith('$(') && name.endsWith(')')) {
    name = name.slice(2, -1).trim();
  }

  return ICON_NAME_PATTERN.test(name) ? name : fallback;
}

function getPacePresentation(cfg: vscode.WorkspaceConfiguration, state: PaceState['state']): PacePresentation {
  const config = PACE_CONFIG[state];
  const defaultLabel = t(config.labelKey);

  // 1. 独立覆盖（最高优先级）
  const labelObject = cfg.get<Record<string, string>>('paceLabels', {});
  const fromObject = typeof labelObject?.[state] === 'string' ? labelObject[state] : '';
  const fromLegacy = cfg.get<string>(config.labelSetting, '');

  // 2. 主题预设
  const theme = cfg.get<PaceTheme>('paceTheme', 'Simple');
  const themeKey = (THEME_LABELS[theme] ?? THEME_LABELS['Simple'])[state];
  const themeLabel = t(themeKey);

  const configuredLabel = (fromObject || fromLegacy || themeLabel).trim();
  const label = configuredLabel || defaultLabel;

  // 图标逻辑不变
  const iconObject = cfg.get<Record<string, string>>('paceIcons', {});
  const iconFromObject = typeof iconObject?.[state] === 'string' ? iconObject[state] : '';
  const iconFromLegacy = cfg.get<string>(config.iconSetting, '');
  const configuredIcon = iconFromObject || iconFromLegacy || config.defaultIcon;
  const icon = normalizeIconName(configuredIcon, config.defaultIcon);

  return { label, icon };
}

function restartInterval() {
  if (intervalId) clearInterval(intervalId);

  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const configured = cfg.get<number>('refreshIntervalMinutes', 5);
  const safeMinutes = Number.isFinite(configured) ? Math.max(MIN_REFRESH_MINUTES, configured) : 5;
  intervalId = setInterval(refresh, safeMinutes * 60 * 1000);
}

export function deactivate() {
  if (intervalId) clearInterval(intervalId);
}

async function resolveApiKey(): Promise<string> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const configuredKey = cfg.get<string>('apiKey', '');
  if (configuredKey) return configuredKey;

  if (vscode.workspace.workspaceFolders) {
    for (const folder of vscode.workspace.workspaceFolders) {
      const envPath = vscode.Uri.joinPath(folder.uri, '.env');
      try {
        const envData = await vscode.workspace.fs.readFile(envPath);
        const envText = Buffer.from(envData).toString('utf8');
        const lines = envText.split('\n');
        let fallbackKey = '';
        for (const line of lines) {
          const match = line.match(/^\s*(KIMI_CODING_API_KEY|KIMI_API_KEY)\s*=\s*['"]?([^'"\s]+)['"]?/);
          if (match) {
            if (match[1] === 'KIMI_CODING_API_KEY') return match[2];
            if (!fallbackKey) fallbackKey = match[2];
          }
        }
        if (fallbackKey) return fallbackKey;
      } catch {
        // Continue when .env is absent or unreadable.
      }
    }
  }

  if (process.env.KIMI_CODING_API_KEY) return process.env.KIMI_CODING_API_KEY;
  if (process.env.KIMI_API_KEY) return process.env.KIMI_API_KEY;
  return '';
}

function localizedLimitName(label: string): string {
  const type = detectWindowType(label);

  if (type === 'weekly') return t('Weekly');
  if (type === 'fiveHours') return t('5 Hours');
  if (type === 'monthly') return t('Monthly');
  return label;
}

function findWindowItem(items: UsageItem[], windowType: WindowType): UsageItem | undefined {
  return items.find((item) => detectWindowType(item.label) === windowType);
}

function isLowRemaining(item: UsageItem | undefined, thresholdPercent: number): boolean {
  if (!item) return false;
  return item.percent_left < thresholdPercent;
}

function pushSection(lines: string[], title: string, entries: string[]) {
  if (entries.length === 0) return;
  if (lines.length > 0) lines.push('');
  lines.push(`**${title}**`);
  lines.push(...entries.map((entry) => `- ${entry}`));
}

function isLinkIssue(err: unknown): boolean {
  const raw = String(err ?? '').toLowerCase();
  return raw.includes('invalid url')
    || raw.includes('timeout')
    || raw.includes('enotfound')
    || raw.includes('econnreset')
    || raw.includes('network')
    || raw.includes('socket');
}

function buildErrorPresentation(err: unknown): ErrorPresentation {
  const raw = String(err ?? '');
  const lower = raw.toLowerCase();

  if (lower.includes('timeout')) {
    return {
      text: `🌑  ${t('Can you hear me, Major Kimi?')}`,
      tooltip: `${t('Ground Control to Major Kimi — Planet Earth is blue and there\'s nothing I can do.')}\n${t('Check baseUrl and network link.')}`,
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

  if (lower.includes('enotfound') || lower.includes('econnreset') || lower.includes('network') || lower.includes('socket')) {
    return {
      text: `🌑  ${t('Can you hear me, Major Kimi?')}`,
      tooltip: `${t('Ground Control to Major Kimi — Planet Earth is blue and there\'s nothing I can do.')}\n${t('Check baseUrl and network link.')}`,
      isWarning: false,
    };
  }

  if (lower.includes('invalid url')) {
    return {
      text: `🌑  ${t('Can you hear me, Major Kimi?')}`,
      tooltip: `${t('Ground Control to Major Kimi — Planet Earth is blue and there\'s nothing I can do.')}\n${t('Check baseUrl and network link.')}`,
      isWarning: false,
    };
  }

  return {
    text: `$(error) ${t('Request Failed Short')}`,
    tooltip: `${t('Request Failed Short')}: ${raw.slice(0, 200)}`,
    isWarning: false,
  };
}

async function refresh() {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const apiKey = await resolveApiKey();
  const baseUrl = cfg.get<string>('baseUrl', 'https://api.kimi.com/coding/v1');
  const thresholds = readThresholdSettings(cfg);
  const paceThresholds = readPaceThresholds(cfg);

  if (!apiKey) {
    statusBarItem.text = `$(key) ${t('API Key Missing')}`;
    const missingKeyTooltip = new vscode.MarkdownString(
      [
        `**${t('Ground Control to Major Kimi — Planet Earth is blue and there\'s nothing I can do.')}**`,
        `${t('Set `kimiCodeUsage.apiKey` or `.env` key to reconnect.')}`,
      ].join('\n')
    );
    missingKeyTooltip.isTrusted = false;
    statusBarItem.tooltip = missingKeyTooltip;
    statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    return;
  }

  if (!baseUrl || !baseUrl.trim()) {
    statusBarItem.text = `🌑  ${t('Can you hear me, Major Kimi?')}`;
    statusBarItem.tooltip = `${t('Ground Control to Major Kimi — Planet Earth is blue and there\'s nothing I can do.')}\n${t('Check baseUrl and network link.')}`;
    statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    return;
  }

  try {
    const data = await fetchUsage(baseUrl, apiKey);
    const items = parsePayload(data);

    if (items.length === 0) {
      statusBarItem.text = `$(chip) ${t('Kimi: --')}`;
      statusBarItem.tooltip = t('No usage data');
      statusBarItem.backgroundColor = undefined;
      console.warn('[KimiCodeUsage] API returned empty usage items. Payload structure may have changed.');
      return;
    }

    const weeklyItem = findWindowItem(items, 'weekly');
    const fiveHoursItem = findWindowItem(items, 'fiveHours');

    const showPace = cfg.get<boolean>('showPaceIndicator', true);
    const showPaceBar = cfg.get<boolean>('showPaceBar', true);
    const pace = weeklyItem && showPace ? computePace(weeklyItem, getWindowSeconds(weeklyItem.label), paceThresholds) : null;
    const paceState = pace?.state || 'normal';
    const pacePresentation = getPacePresentation(cfg, paceState);

    const moonEmoji = (() => {
      const quotaItems = [weeklyItem, fiveHoursItem].filter(Boolean) as UsageItem[];
      for (const item of quotaItems) {
        if (item.percent_left >= 99) return '🌕';
        if (item.percent_left <= 1) return '🌑';
      }
      return paceState === 'fast' ? '🌒' : paceState === 'normal' ? '🌓' : '🌔';
    })();

    let paceBarStr = '';
    if (showPaceBar) {
      paceBarStr = pace ? formatPaceBar(pace.ratio, paceThresholds) : '▰▰▱';
    }

    const suffix = showPace ? `> $(${pacePresentation.icon}) ${pacePresentation.label}` : '';

    const parts = items.map((i) => `${shortLabel(i.label)}:${i.percent_left.toFixed(0)}%`);
    const prefix = paceBarStr
      ? `${moonEmoji}  ${paceBarStr}  ${parts.join(' ')}`.trim()
      : `${moonEmoji}  ${parts.join(' ')}`.trim();
    statusBarItem.text = `${prefix} ${suffix}`.trim();

    const redAlertCondition = cfg.get<'Weekly' | '5 Hours' | 'Either'>('redAlertCondition', 'Either');
    const lowWeekly = isLowRemaining(weeklyItem, thresholds.weekly);
    const lowFiveHours = isLowRemaining(fiveHoursItem, thresholds.fiveHours);
    const thresholdRed = redAlertCondition === 'Weekly' ? lowWeekly
      : redAlertCondition === '5 Hours' ? lowFiveHours
      : lowWeekly || lowFiveHours;
    const shouldRed = pace?.state === 'fast' || thresholdRed;

    statusBarItem.backgroundColor = shouldRed
      ? new vscode.ThemeColor('statusBarItem.errorBackground')
      : undefined;

    const overviewEntries = items.map((item) => `${localizedLimitName(item.label)}: ${item.percent_left.toFixed(0)}% ${t('left')}`);

    const resetEntries: string[] = [];
    for (const item of items) {
      const name = localizedLimitName(item.label);
      if (item.reset_at) {
        const formatted = formatResetTimeAbsolute(item.reset_at);
        const line = t('{0}: Fuel: {1} | Refuel: {2}', name, formatted.relative, formatted.absolute);
        resetEntries.push(line);
      } else if (item.reset_hint) {
        resetEntries.push(`${name}: ${item.reset_hint}`);
      }
    }

    const paceEntries: string[] = [];
    if (showPace) {
      for (const item of items) {
        const itemPace = computePace(item, getWindowSeconds(item.label), paceThresholds);
        if (!itemPace) continue;
        const itemPacePresentation = getPacePresentation(cfg, itemPace.state);
        const rawDeviation = (itemPace.ratio - 1.0) * 100;
        const deviation = rawDeviation.toFixed(2);
        const sign = rawDeviation > 0 ? '+' : '';
        paceEntries.push(`${localizedLimitName(item.label)}: ${sign}${deviation}% ($(${itemPacePresentation.icon}) ${itemPacePresentation.label})`);
      }
    }

    const markdownLines: string[] = [];
    pushSection(markdownLines, t('Usage Telemetry'), overviewEntries);
    pushSection(markdownLines, t('Pace Details'), paceEntries);
    pushSection(markdownLines, t('Reset Schedule'), resetEntries);

    const tooltip = new vscode.MarkdownString(markdownLines.join('\n'));
    tooltip.supportThemeIcons = true;
    statusBarItem.tooltip = tooltip;
  } catch (err) {
    const errorView = buildErrorPresentation(err);
    statusBarItem.text = errorView.text;
    statusBarItem.tooltip = errorView.tooltip;
    statusBarItem.backgroundColor = errorView.isWarning
      ? new vscode.ThemeColor('statusBarItem.errorBackground')
      : undefined;
  }
}

function fetchUsage(baseUrl: string, apiKey: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const url = new URL(baseUrl + '/usages');
    const req = https.get(
      url,
      {
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'User-Agent': 'kimi-usage-vscode/0.1.8',
        },
        timeout: 10000,
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(JSON.parse(body));
            } catch {
              reject(new Error(t('Invalid JSON response')));
            }
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 200)}`));
          }
        });
      }
    );

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(t('Request timeout')));
    });
  });
}

function parsePayload(payload: unknown): UsageItem[] {
  const data = payload as Record<string, unknown>;
  const items: UsageItem[] = [];

  const usage = data?.usage;
  if (usage && typeof usage === 'object') {
    const row = toRow(usage as Record<string, unknown>, t('Weekly limit'));
    if (row) items.push(row);
  }

  const limits = data?.limits;
  if (Array.isArray(limits)) {
    for (let i = 0; i < limits.length; i++) {
      const item = limits[i];
      if (!item || typeof item !== 'object') continue;

      const itemObj = item as Record<string, unknown>;
      const detail = (itemObj.detail && typeof itemObj.detail === 'object'
        ? itemObj.detail
        : itemObj) as Record<string, unknown>;

      const label = limitLabel(itemObj, detail, (itemObj.window as Record<string, unknown>) || {}, i);
      const row = toRow(detail, label);
      if (row) items.push(row);
    }
  }

  return items;
}

function toRow(data: Record<string, unknown>, defaultLabel: string): UsageItem | null {
  const limit = toInt(data.limit);
  let used = toInt(data.used);

  if (used == null) {
    const remaining = toInt(data.remaining);
    if (remaining != null && limit != null) used = limit - remaining;
  }
  if (used == null && limit == null) return null;

  const u = used ?? 0;
  const l = limit ?? 0;

  let reset_seconds: number | null = null;
  for (const key of ['reset_in', 'resetIn', 'ttl']) {
    const s = toInt(data[key]);
    if (s != null) {
      reset_seconds = s;
      break;
    }
  }

  if (reset_seconds == null) {
    for (const key of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
      const v = data[key];
      if (!v) continue;
      const sec = secondsUntil(String(v));
      if (sec != null && sec > 0) {
        reset_seconds = sec;
        break;
      }
    }
  }

  let reset_at: string | null = null;
  for (const key of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
    const v = data[key];
    if (v) {
      reset_at = String(v);
      break;
    }
  }

  return {
    label: String(data.name || data.title || defaultLabel),
    used: u,
    limit: l,
    remaining: l - u,
    percent_left: l > 0 ? ((l - u) / l) * 100 : 0,
    reset_hint: resetHint(data),
    reset_seconds,
    reset_at,
  };
}

function limitLabel(item: Record<string, unknown>, detail: Record<string, unknown>, window: Record<string, unknown>, idx: number): string {
  for (const key of ['name', 'title', 'scope']) {
    const value = item[key] ?? detail[key];
    if (value) return String(value);
  }

  const duration = toInt(window.duration ?? item.duration ?? detail.duration);
  const timeUnit = String(window.timeUnit ?? item.timeUnit ?? detail.timeUnit ?? '');

  if (duration != null) {
    if (timeUnit.includes('MINUTE')) {
      return duration >= 60 && duration % 60 === 0
        ? `${Math.floor(duration / 60)}h limit`
        : `${duration}m limit`;
    }
    if (timeUnit.includes('HOUR')) return `${duration}h limit`;
    if (timeUnit.includes('DAY')) return `${duration}d limit`;
    return `${duration}s limit`;
  }

  return `Limit #${idx + 1}`;
}

function resetHint(data: Record<string, unknown>): string | null {
  for (const key of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
    const v = data[key];
    if (v) return formatResetTime(String(v));
  }
  for (const key of ['reset_in', 'resetIn', 'ttl', 'window']) {
    const s = toInt(data[key]);
    if (s) return t('Resets in {0}', formatDuration(s));
  }
  return null;
}

function normalizeIso(val: string): string {
  let iso = val;
  if (iso.includes('.') && iso.endsWith('Z')) {
    const [base, frac] = iso.slice(0, -1).split('.');
    iso = `${base}.${frac.slice(0, 6)}Z`;
  }
  return iso;
}

function secondsUntil(val: string): number | null {
  try {
    const iso = normalizeIso(val);
    const dt = new Date(iso.replace('Z', '+00:00'));
    if (Number.isNaN(dt.getTime())) return null;
    return Math.floor((dt.getTime() - Date.now()) / 1000);
  } catch {
    return null;
  }
}

function formatResetTime(val: string): string {
  const sec = secondsUntil(val);
  if (sec == null) return t('Resets at {0}', val);
  if (sec <= 0) return t('Reset');
  return t('Resets in {0}', formatDuration(sec));
}

function formatDuration(seconds: number): string {
  const parts: string[] = [];

  const days = Math.floor(seconds / 86400);
  if (days) parts.push(`${days}${t('day-short')}`);

  const rem = seconds % 86400;
  const hours = Math.floor(rem / 3600);
  if (hours) parts.push(`${hours}${t('hour-short')}`);

  const mins = Math.floor((rem % 3600) / 60);
  if (mins) parts.push(`${mins}${t('minute-short')}`);

  const secs = rem % 60;
  if (secs && !parts.length) parts.push(`${secs}${t('second-short')}`);

  return parts.join(' ') || `0${t('second-short')}`;
}

function formatResetTimeAbsolute(val: string): { absolute: string; relative: string } {
  try {
    const iso = normalizeIso(val);
    const dt = new Date(iso.replace('Z', '+00:00'));
    if (Number.isNaN(dt.getTime())) {
      return { absolute: val, relative: t('Unknown') };
    }

    const now = new Date();
    const sec = Math.floor((dt.getTime() - now.getTime()) / 1000);
    const relative = sec <= 0 ? t('Reset') : formatDuration(sec);

    const hours = dt.getHours().toString().padStart(2, '0');
    const mins = dt.getMinutes().toString().padStart(2, '0');

    const resetDay = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);

    if (resetDay.getTime() === today.getTime()) {
      return { absolute: t('Today {0}:{1}', hours, mins), relative };
    }
    if (resetDay.getTime() === tomorrow.getTime()) {
      return { absolute: t('Tomorrow {0}:{1}', hours, mins), relative };
    }

    const weekdays = [t('Sun'), t('Mon'), t('Tue'), t('Wed'), t('Thu'), t('Fri'), t('Sat')];
    return { absolute: `${weekdays[dt.getDay()]} ${hours}:${mins}`, relative };
  } catch {
    return { absolute: val, relative: t('Unknown') };
  }
}

function toInt(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function shortLabel(label: string): string {
  const type = detectWindowType(label);

  if (type === 'weekly') return t('W-Short');
  if (type === 'fiveHours') return t('5H-Short');
  if (type === 'monthly') return t('M-Short');
  return label.slice(0, 3);
}

async function showDetails() {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const apiKey = await resolveApiKey();
  const baseUrl = cfg.get<string>('baseUrl', 'https://api.kimi.com/coding/v1');

  if (!apiKey) {
    vscode.window.showWarningMessage(`${t('Can you hear me, Major Kimi?')}\n${t('Set `kimiCodeUsage.apiKey` or `.env` key to reconnect.')}`);
    return;
  }

  if (!baseUrl || !baseUrl.trim()) {
    vscode.window.showWarningMessage(`${t('Can you hear me, Major Kimi?')}\n${t('Check baseUrl and network link.')}`);
    return;
  }

  try {
    const data = await fetchUsage(baseUrl, apiKey);
    const items = parsePayload(data);
    const paceThresholds = readPaceThresholds(cfg);
    const showPace = cfg.get<boolean>('showPaceIndicator', true);

    const picks: vscode.QuickPickItem[] = items.map((item) => {
      const displayName = localizedLimitName(item.label);
      const label = `${displayName}: ${item.percent_left.toFixed(0)}% ${t('left')}`;
      const segments: string[] = [];
      let detail = '';

      if (showPace) {
        const pace = computePace(item, getWindowSeconds(item.label), paceThresholds);
        if (pace) {
          const rawDeviation = (pace.ratio - 1.0) * 100;
          const deviation = rawDeviation.toFixed(2);
          const sign = rawDeviation > 0 ? '+' : '';
          const pacePresentation = getPacePresentation(cfg, pace.state);
          segments.push(`${t('Current Pace')}: ${sign}${deviation}%`);
          segments.push(`$(${pacePresentation.icon}) ${pacePresentation.label}`);
        }
      }

      if (item.reset_at) {
        const formatted = formatResetTimeAbsolute(item.reset_at);
        detail = t('Resets {0} (in {1})', formatted.absolute, formatted.relative);
      } else if (item.reset_hint) {
        detail = item.reset_hint;
      }

      return {
        label,
        description: segments.join('  •  '),
        detail,
      };
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
    quickPick.buttons = [settingsButton];

    quickPick.onDidTriggerButton((button) => {
      if (button.tooltip === settingsButton.tooltip) {
        vscode.commands.executeCommand('workbench.action.openSettings', 'kimiCodeUsage');
        quickPick.hide();
      }
    });

    quickPick.onDidAccept(() => {
      quickPick.hide();
    });

    quickPick.show();
  } catch (err) {
    const rawLower = String(err ?? '').toLowerCase();
    if (isLinkIssue(err)) {
      vscode.window.showWarningMessage(`${t('Can you hear me, Major Kimi?')}\n${t('Check baseUrl and network link.')}`);
      return;
    }
    if (rawLower.includes('http 5')) {
      vscode.window.showWarningMessage(`${t('Server error from Kimi API. Please retry shortly.')}: ${String(err ?? '').slice(0, 200)}`);
      return;
    }
    const raw = String(err ?? '');
    vscode.window.showWarningMessage(`${t('Usage fetch failed')}: ${raw.slice(0, 200)}`);
  }
}
