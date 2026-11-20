import type { UsageItem } from '../types';
import { t } from '../i18n';
import { getUserAgentVersion } from '../userAgent';
import { httpGetJson } from '../httpJson';
import type { ProviderAdapter, ProviderSpec } from './types';

const SPEC: ProviderSpec = {
  id: 'openrouter',
  displayName: 'OpenRouter',
  keyEnv: 'OPENROUTER_API_KEY',
  baseUrlEnv: 'OPENROUTER_BASE_URL',
  defaultBaseUrl: 'https://openrouter.ai/api',
  windows: [],
};

/** Port of Python `_base_url_v1`: strip trailing slash, ensure `/v1` suffix. */
export function baseUrlV1(baseUrl: string): string {
  const base = baseUrl.replace(/\/+$/, '');
  return base.endsWith('/v1') ? base : `${base}/v1`;
}

async function getJson(url: string, apiKey: string): Promise<unknown> {
  const resp = await httpGetJson(url, apiKey, getUserAgentVersion());
  if (resp.status < 200 || resp.status >= 300) {
    throw new Error(`OpenRouter API Error HTTP ${resp.status}: ${resp.body}`);
  }
  if (resp.json === null && resp.body.trim() !== '') {
    throw new Error(t('Invalid JSON response'));
  }
  return resp.json;
}

function toNum(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function num(v: unknown, fallback = 0): number {
  return toNum(v) ?? fallback;
}

/** Money row without a limit: show a literal text value instead of a fabricated percentage. */
export function moneyRow(label: string, used: number, limit: number | null): UsageItem {
  if (limit == null || limit <= 0) {
    return {
      label,
      used,
      limit: 0,
      remaining: 0,
      percent_left: 0,
      reset_hint: null,
      reset_seconds: null,
      reset_at: null,
      text_value: `$${used.toFixed(2)} used`,
    };
  }
  return {
    label,
    used,
    limit,
    remaining: limit - used,
    percent_left: clampPercent(((limit - used) / limit) * 100),
    reset_hint: null,
    reset_seconds: null,
    reset_at: null,
  };
}

function clampPercent(v: number): number {
  return Math.max(0, Math.min(100, v));
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

/** Port of the Python rate-limit row: `Unlimited/{interval}` vs `{reqs} req/{interval}`. */
export function rateLimitText(requests: unknown, interval: unknown): string {
  const reqs = toNum(requests);
  if (reqs == null || interval == null) return '';
  const iv = String(interval);
  if (reqs === -1) return `Unlimited/${iv}`;
  return `${reqs} req/${iv}`;
}

/** Port of the Python usage row: `Daily: $x | Weekly: $y | Monthly: $z`. */
export function usageText(daily: unknown, weekly: unknown, monthly: unknown): string {
  const d = num(daily).toFixed(4);
  const w = num(weekly).toFixed(4);
  const m = num(monthly).toFixed(4);
  return `Daily: $${d} | Weekly: $${w} | Monthly: $${m}`;
}

export const openrouterProvider: ProviderAdapter = {
  spec: SPEC,
  async fetch(apiKey: string, baseUrl: string): Promise<UsageItem[]> {
    const base = baseUrlV1(baseUrl);
    const keyPayload = (await getJson(`${base}/auth/key`, apiKey)) as Record<string, unknown> | null;
    const keyData = (keyPayload?.data ?? {}) as Record<string, unknown>;

    let creditsData: Record<string, unknown> | null;
    try {
      const creditsPayload = (await getJson(`${base}/credits`, apiKey)) as Record<string, unknown> | null;
      const data = creditsPayload?.data;
      creditsData =
        data != null && typeof data === 'object' && !Array.isArray(data)
          ? (data as Record<string, unknown>)
          : null;
    } catch {
      creditsData = null; // credits is optional; ignore failures like the Python port
    }

    const res: UsageItem[] = [];
    const keyUsage = toNum(keyData.usage);
    const keyLimit = toNum(keyData.limit);
    const keyUsed = keyUsage ?? 0;

    if (creditsData && creditsData.total_credits != null && creditsData.total_usage != null) {
      const totalCredits = num(creditsData.total_credits);
      const totalUsage = num(creditsData.total_usage);
      res.push(moneyRow(t('Credits'), totalUsage, totalCredits));
      res.push(moneyRow(t('Key Usage'), keyUsed, keyLimit));
    } else {
      res.push(moneyRow(t('Credits'), keyUsed, keyLimit));
    }

    const keyLabel = keyData.label;
    if (typeof keyLabel === 'string' && keyLabel) {
      const isManagement = Boolean(keyData.is_management_key);
      const displayName = isManagement ? t('Management Key') : t('Key Name');
      const displayValue = keyLabel.includes('...') ? keyLabel.replace(/\.\.\./g, '*********') : keyLabel;
      res.push(textRow(displayName, displayValue));
    }

    if (keyData.is_free_tier != null) {
      res.push(textRow(t('Free Tier'), keyData.is_free_tier === true ? t('Yes') : t('No')));
    }

    const limitReset: unknown = keyData.limit_reset;
    if (typeof limitReset === 'string' && limitReset.length > 0) {
      res.push(textRow(t('Limit Reset'), limitReset));
    }

    const expiresAt: unknown = keyData.expires_at;
    if (typeof expiresAt === 'string' && expiresAt.length > 0) {
      res.push(textRow(t('Expires At'), expiresAt));
    }

    const rateLimit = keyData.rate_limit;
    if (rateLimit != null && typeof rateLimit === 'object' && !Array.isArray(rateLimit)) {
      const rl = rateLimit as Record<string, unknown>;
      const text = rateLimitText(rl.requests, rl.interval);
      if (text) res.push(textRow(t('Rate Limit'), text));
    }

    res.push(
      textRow(t('Usage'), usageText(keyData.usage_daily, keyData.usage_weekly, keyData.usage_monthly)),
    );

    return res;
  },
};
