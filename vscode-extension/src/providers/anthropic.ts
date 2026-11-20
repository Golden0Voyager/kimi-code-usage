import type { UsageItem } from '../types';
import { t } from '../i18n';
import { getUserAgentVersion } from '../userAgent';
import { httpGetJson } from '../httpJson';
import type { ProviderAdapter, ProviderSpec } from './types';

const SPEC: ProviderSpec = {
  id: 'anthropic',
  displayName: 'Anthropic',
  keyEnv: 'ANTHROPIC_API_KEY',
  baseUrlEnv: 'ANTHROPIC_BASE_URL',
  defaultBaseUrl: 'https://api.anthropic.com',
  windows: ['fiveHours'],
};

export const ANTHROPIC_UNREADABLE_KEY_HINT =
  'This key cannot read Anthropic usage: /api/oauth/usage only accepts a Claude Code OAuth token. Use the claude provider for subscription quotas.';

function percentRow(label: string, utilization: unknown): UsageItem {
  const raw = Number(utilization);
  const pct = Math.max(0, Math.min(100, (Number.isFinite(raw) ? raw : 0) * 100));
  return {
    label,
    used: pct,
    limit: 100,
    remaining: 100 - pct,
    percent_left: 100 - pct,
    reset_hint: null,
    reset_seconds: null,
    reset_at: null,
  };
}

function textRow(label: string, text: string): UsageItem {
  return {
    label,
    used: 0,
    limit: 0,
    remaining: 0,
    percent_left: 0,
    reset_hint: null,
    reset_seconds: null,
    reset_at: null,
    text_value: text,
  };
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v == null || typeof v !== 'object' || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

export const anthropicProvider: ProviderAdapter = {
  spec: SPEC,
  async fetch(apiKey: string, baseUrl: string): Promise<UsageItem[]> {
    const url = `${baseUrl.replace(/\/+$/, '')}/api/oauth/usage`;
    const resp = await httpGetJson(url, apiKey, getUserAgentVersion());

    if (resp.status === 401 || resp.status === 403) {
      return [textRow(t('API Plan'), t(ANTHROPIC_UNREADABLE_KEY_HINT))];
    }
    if (resp.status < 200 || resp.status >= 300) {
      throw new Error(`Anthropic API Error HTTP ${resp.status}: ${resp.body.slice(0, 500)}`);
    }

    const data = asRecord(resp.json) ?? {};
    const fiveHour = asRecord(data.five_hour);
    const sevenDay = asRecord(data.seven_day);

    return [
      percentRow(t('5 Hours'), fiveHour?.utilization ?? 0),
      percentRow(t('7 Days'), sevenDay?.utilization ?? 0),
    ];
  },
};
