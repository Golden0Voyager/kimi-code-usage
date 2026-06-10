import * as vscode from 'vscode';
import {
  MIN_ELAPSED_SECONDS_FOR_PACE,
  PACE_RATIO_CAP,
  type PacePresentation,
  type PaceSensitivity,
  type PaceState,
  type PaceStateLabel,
  type PaceTheme,
  type ThresholdConfig,
  type UsageItem,
  ICON_NAME_PATTERN,
} from './types';
import { t } from './i18n';

export const THEME_LABELS: Record<PaceTheme, Record<PaceStateLabel, string>> = {
  Simple: { fast: 'Fast', normal: 'Normal', slow: 'Slow' },
  Animals: { fast: 'Cheetah', normal: 'Lynx', slow: 'Sloth' },
  Fish: { fast: 'Marlin', normal: 'Dolphin', slow: 'Turtle' },
  Birds: { fast: 'Peregrine', normal: 'Eagle', slow: 'Ostrich' },
  Racing: { fast: 'Nitro', normal: 'Cruise', slow: 'Idle' },
  Running: { fast: 'Sprint', normal: 'Jog', slow: 'Walk' },
  F1: { fast: 'Overtake Mode', normal: 'Race Pace', slow: 'Safety Car' },
  'Star Wars': { fast: 'Falcon', normal: 'X-Wing', slow: 'Shuttle' },
  'Star Trek': { fast: 'Defiant', normal: 'Enterprise', slow: 'Voyager' },
  'Back To The Future': { fast: 'Flux', normal: 'Driving', slow: 'Parked' },
  'Pink Floyd': { fast: 'Eclipse', normal: 'Time', slow: 'Breathe' },
  Submarine: { fast: 'Alfa', normal: 'Ohio', slow: 'U-Boat' },
  Airliner: { fast: 'Concorde', normal: 'A350', slow: 'Comet' },
  Fighter: { fast: 'SR-71', normal: 'F-22', slow: 'A-10' },
  Firearms: { fast: 'Minigun', normal: 'AK-47', slow: 'Revolver' },
  Rocket: { fast: 'Thrust', normal: 'Propulsion', slow: 'Hover' },
};

export const SENSITIVITY_THRESHOLDS: Record<Exclude<PaceSensitivity, 'Custom'>, ThresholdConfig> = {
  Relaxed: { fast: 1.2, slow: 0.8 },
  Normal: { fast: 1.12, slow: 0.88 },
  Strict: { fast: 1.05, slow: 0.95 },
};

const PACE_CONFIG: Record<
  PaceStateLabel,
  { labelKey: string; labelSetting: string; iconSetting: string; defaultIcon: string }
> = {
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
};

export function computePace(
  item: UsageItem,
  windowSeconds: number,
  thresholds: ThresholdConfig,
): PaceState | null {
  if (!item.reset_seconds || item.reset_seconds <= 0) return null;
  if (item.limit <= 0) return null;

  const elapsed = windowSeconds - item.reset_seconds;
  if (elapsed <= 0 || elapsed < MIN_ELAPSED_SECONDS_FOR_PACE) return null;

  const actualUsedRatio = item.used / item.limit;
  const elapsedRatio = elapsed / windowSeconds;

  const rawRatio = actualUsedRatio / elapsedRatio;
  const ratio = Math.min(rawRatio, PACE_RATIO_CAP);

  let state: PaceStateLabel;
  if (ratio >= thresholds.fast) state = 'fast';
  else if (ratio <= thresholds.slow) state = 'slow';
  else state = 'normal';

  return { ratio, state };
}

export function formatPaceBar(ratio: number, thresholds: ThresholdConfig): string {
  let filled: number;
  if (ratio >= thresholds.fast) filled = 3;
  else if (ratio >= thresholds.slow) filled = 2;
  else filled = 1;
  return '\u25B0'.repeat(filled) + '\u25B1'.repeat(3 - filled);
}

export function normalizeIconName(raw: string, fallback: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return fallback;

  let name = trimmed;
  if (name.startsWith('$(') && name.endsWith(')')) {
    name = name.slice(2, -1).trim();
  }

  return ICON_NAME_PATTERN.test(name) ? name : fallback;
}

export function getPacePresentation(
  cfg: vscode.WorkspaceConfiguration,
  state: PaceStateLabel,
): PacePresentation {
  const config = PACE_CONFIG[state];
  const defaultLabel = t(config.labelKey);

  const labelObject = (cfg.get<Record<string, string>>('paceLabels') ?? {}) as Record<string, string>;
  const fromObject = typeof labelObject[state] === 'string' ? labelObject[state] : '';
  const fromLegacy = cfg.get<string>(config.labelSetting, '');

  const theme = cfg.get<PaceTheme>('paceTheme', 'Simple');
  const themeKey = (THEME_LABELS[theme] ?? THEME_LABELS['Simple'])[state];
  const themeLabel = t(themeKey);

  const configuredLabel = (fromObject || fromLegacy || themeLabel).trim();
  const label = configuredLabel || defaultLabel;

  const iconObject = (cfg.get<Record<string, string>>('paceIcons') ?? {}) as Record<string, string>;
  const iconFromObject = typeof iconObject[state] === 'string' ? iconObject[state] : '';
  const iconFromLegacy = cfg.get<string>(config.iconSetting, '');
  const configuredIcon = iconFromObject || iconFromLegacy || config.defaultIcon;
  const icon = normalizeIconName(configuredIcon, config.defaultIcon);

  return { label, icon };
}

export function paceConfigFor(state: PaceStateLabel) {
  return PACE_CONFIG[state];
}
