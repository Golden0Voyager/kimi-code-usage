import * as vscode from 'vscode';
import {
  DEFAULT_HISTORY_RETENTION_DAYS,
  DEFAULT_LOW_THRESHOLD,
  type PaceSensitivity,
  type ThresholdConfig,
  type ThresholdSettings,
} from './types';
import { SENSITIVITY_THRESHOLDS } from './pace';

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
      : SENSITIVITY_THRESHOLDS[sensitivity];

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
  const preset = SENSITIVITY_THRESHOLDS[sensitivity];
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
