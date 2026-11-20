import * as vscode from 'vscode';
import {
  DEFAULT_HISTORY_RETENTION_DAYS,
  DEFAULT_LOW_THRESHOLD,
  type PaceSensitivity,
  type ThresholdConfig,
  type ThresholdSettings,
} from './types';
import { SENSITIVITY_THRESHOLDS } from './pace';
import type { ProviderId } from './providers/types';
import { getProvider, isProviderId, PROVIDER_IDS } from './providers/registry';

export function sanitizePercentThreshold(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  const numeric = value as number;
  return Math.max(0, Math.min(100, numeric));
}

export function readThresholdSettings(cfg: vscode.WorkspaceConfiguration): ThresholdSettings {
  return {
    weekly: sanitizePercentThreshold(
      cfg.get<number>('weeklyLowThresholdPercent', DEFAULT_LOW_THRESHOLD),
      DEFAULT_LOW_THRESHOLD,
    ),
    fiveHours: sanitizePercentThreshold(
      cfg.get<number>('fiveHourLowThresholdPercent', DEFAULT_LOW_THRESHOLD),
      DEFAULT_LOW_THRESHOLD,
    ),
  };
}

export function sanitizeHistoryRetentionDays(
  value: number | undefined,
  fallback = DEFAULT_HISTORY_RETENTION_DAYS,
): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(1, Math.min(365, Math.floor(value as number)));
}

export function readHistoryRetentionDays(cfg: vscode.WorkspaceConfiguration): number {
  return sanitizeHistoryRetentionDays(
    cfg.get<number>('historyRetentionDays', DEFAULT_HISTORY_RETENTION_DAYS),
    DEFAULT_HISTORY_RETENTION_DAYS,
  );
}

export function readPaceThresholds(cfg: vscode.WorkspaceConfiguration): ThresholdConfig {
  const sensitivity = cfg.get<PaceSensitivity>('paceSensitivity', 'Normal');
  const preset =
    sensitivity === 'Custom'
      ? SENSITIVITY_THRESHOLDS.Normal
      : ((SENSITIVITY_THRESHOLDS[sensitivity] as typeof SENSITIVITY_THRESHOLDS.Normal | undefined) ??
        SENSITIVITY_THRESHOLDS.Normal);

  const customFast = cfg.get<number>('paceThresholdFast');
  const customSlow = cfg.get<number>('paceThresholdSlow');

  return {
    fast: Number.isFinite(customFast) ? customFast! : preset.fast,
    slow: Number.isFinite(customSlow) ? customSlow! : preset.slow,
  };
}

export function detectSensitivityFromThresholds(fast: number, slow: number): PaceSensitivity {
  for (const [key, preset] of Object.entries(SENSITIVITY_THRESHOLDS)) {
    if (preset.fast === fast && preset.slow === slow) {
      return key as PaceSensitivity;
    }
  }
  return 'Custom';
}

export async function syncSensitivityToThresholds(
  cfg: vscode.WorkspaceConfiguration,
  sensitivity: PaceSensitivity,
): Promise<void> {
  if (sensitivity === 'Custom') return;
  const preset =
    (SENSITIVITY_THRESHOLDS[sensitivity] as typeof SENSITIVITY_THRESHOLDS.Normal | undefined) ??
    SENSITIVITY_THRESHOLDS.Normal;
  await cfg.update('paceThresholdFast', preset.fast, true);
  await cfg.update('paceThresholdSlow', preset.slow, true);
}

export async function resolveApiKey(): Promise<string> {
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
            if (match[1]! === 'KIMI_CODING_API_KEY') return match[2]!;
            if (!fallbackKey) fallbackKey = match[2]!;
          }
        }
        if (fallbackKey) return fallbackKey;
      } catch {
        // .env missing or unreadable — try next folder.
      }
    }
  }

  if (process.env.KIMI_CODING_API_KEY) return process.env.KIMI_CODING_API_KEY;
  if (process.env.KIMI_API_KEY) return process.env.KIMI_API_KEY;
  return '';
}

export interface ProviderSettings {
  enabled: boolean;
  /** Empty string means unconfigured. */
  apiKey: string;
  baseUrl: string;
}

const KEY_FOR: Record<ProviderId, { apiKey: string; baseUrl: string; enabled: string }> = {
  kimi: { apiKey: 'apiKey', baseUrl: 'baseUrl', enabled: 'kimiEnabled' },
  openrouter: {
    apiKey: 'openrouterApiKey',
    baseUrl: 'openrouterBaseUrl',
    enabled: 'openrouterEnabled',
  },
  anthropic: {
    apiKey: 'anthropicApiKey',
    baseUrl: 'anthropicBaseUrl',
    enabled: 'anthropicEnabled',
  },
  openai: { apiKey: 'openaiApiKey', baseUrl: 'openaiBaseUrl', enabled: 'openaiEnabled' },
};

/**
 * Read one provider's flat settings. `apiKey` falls back to the provider's env
 * var; `baseUrl` falls back to the spec default. Kimi keeps its legacy
 * `.env`-scanning behaviour in `resolveApiKey`, which callers still use.
 */
export function readProviderSettings(cfg: vscode.WorkspaceConfiguration, id: ProviderId): ProviderSettings {
  const keys = KEY_FOR[id];
  const spec = getProvider(id).spec;
  const configuredKey = cfg.get<string>(keys.apiKey, '');
  const apiKey = configuredKey !== '' ? configuredKey : (process.env[spec.keyEnv] ?? '');
  const configuredBase = cfg.get<string>(keys.baseUrl, '');
  const baseUrl =
    configuredBase !== '' ? configuredBase : (process.env[spec.baseUrlEnv] ?? spec.defaultBaseUrl);
  const enabled = cfg.get<boolean>(keys.enabled, id === 'kimi');
  return { enabled, apiKey, baseUrl };
}

export function readPrimaryProvider(cfg: vscode.WorkspaceConfiguration): ProviderId {
  const raw = cfg.get<string>('primaryProvider', 'kimi');
  return isProviderId(raw) ? raw : 'kimi';
}

/** Enabled provider ids with the primary provider always first. */
export function enabledProviders(cfg: vscode.WorkspaceConfiguration): ProviderId[] {
  const primary = readPrimaryProvider(cfg);
  const res: ProviderId[] = [primary];
  for (const id of PROVIDER_IDS) {
    if (id === primary) continue;
    if (readProviderSettings(cfg, id).enabled) res.push(id);
  }
  return res;
}

/**
 * Write an API key (or empty string to clear) to user settings. Global, not
 * Workspace: keys are personal credentials and must not land in the repo.
 */
export async function writeProviderApiKey(id: ProviderId, key: string): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  await cfg.update(KEY_FOR[id].apiKey, key, vscode.ConfigurationTarget.Global);
}

export async function writeProviderBaseUrl(id: ProviderId, baseUrl: string): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  await cfg.update(KEY_FOR[id].baseUrl, baseUrl, vscode.ConfigurationTarget.Global);
}

export async function setProviderEnabled(id: ProviderId, on: boolean): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  await cfg.update(KEY_FOR[id].enabled, on, vscode.ConfigurationTarget.Global);
}
