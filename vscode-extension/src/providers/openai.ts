import type { UsageItem } from '../types';
import { t } from '../i18n';
import { getUserAgentVersion } from '../userAgent';
import { httpGetJson } from '../httpJson';
import type { ProviderAdapter, ProviderSpec } from './types';

const SPEC: ProviderSpec = {
  id: 'openai',
  displayName: 'OpenAI',
  keyEnv: 'OPENAI_API_KEY',
  baseUrlEnv: 'OPENAI_BASE_URL',
  defaultBaseUrl: 'https://api.openai.com',
  windows: [],
};

export const OPENAI_ORG_KEY_HINT =
  'OpenAI organization usage API returned 401/403. This endpoint requires an Org Admin API key (platform.openai.com → Settings → API Keys, role: Org Admin) — a regular sk-... project key is not enough. ChatGPT Plus/Pro subscriptions have no usage API at all; disable this provider with openaiEnabled=false.';

function yyyyMmDd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Month window from the Python port: first day of current month through tomorrow. */
export function monthWindow(now: Date): { start: string; end: string } {
  const start = yyyyMmDd(new Date(now.getFullYear(), now.getMonth(), 1));
  const end = yyyyMmDd(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
  return { start, end };
}

/** Port of the Python URL rule: keep `/v1` if present, else insert it. */
export function baseUrlV1(baseUrl: string): string {
  const base = baseUrl.replace(/\/+$/, '');
  return base.endsWith('/v1') ? base : `${base}/v1`;
}

function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function tokensRow(used: number): UsageItem {
  return {
    label: t('Tokens'),
    used,
    limit: 0,
    remaining: 0,
    percent_left: 0,
    reset_hint: null,
    reset_seconds: null,
    reset_at: null,
    text_value: `${used.toLocaleString('en-US')} tokens`,
  };
}

function costRow(used: number): UsageItem {
  return {
    label: t('Cost'),
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

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function sumTokens(data: unknown): { input: number; output: number } {
  let input = 0;
  let output = 0;
  const root = data != null && typeof data === 'object' ? (data as Record<string, unknown>) : null;
  for (const bucket of asArray(root?.data)) {
    if (bucket == null || typeof bucket !== 'object') continue;
    const row = bucket as Record<string, unknown>;
    input += num(row.input_tokens);
    output += num(row.output_tokens);
  }
  return { input, output };
}

function sumCosts(data: unknown): number {
  let total = 0;
  const root = data != null && typeof data === 'object' ? (data as Record<string, unknown>) : null;
  for (const item of asArray(root?.data)) {
    if (item == null || typeof item !== 'object') continue;
    const amount = (item as Record<string, unknown>).amount;
    if (amount != null && typeof amount === 'object' && !Array.isArray(amount)) {
      const val = (amount as Record<string, unknown>).value;
      if (val != null) total += num(val);
    }
  }
  return total;
}

export const openaiProvider: ProviderAdapter = {
  spec: SPEC,
  async fetch(apiKey: string, baseUrl: string): Promise<UsageItem[]> {
    const base = baseUrlV1(baseUrl);
    const { start, end } = monthWindow(new Date());
    const query = `?start_time=${start}&end_time=${end}`;

    const completions = await httpGetJson(
      `${base}/organization/usage/completions${query}`,
      apiKey,
      getUserAgentVersion(),
    );

    if (completions.status === 401 || completions.status === 403) {
      throw new Error(t(OPENAI_ORG_KEY_HINT));
    }
    if (completions.status < 200 || completions.status >= 300) {
      throw new Error(`OpenAI API Error HTTP ${completions.status}: ${completions.body}`);
    }

    let cost = 0;
    try {
      const costs = await httpGetJson(
        `${base}/organization/usage/costs${query}`,
        apiKey,
        getUserAgentVersion(),
      );
      if (costs.status >= 200 && costs.status < 300) {
        cost = sumCosts(costs.json);
      }
    } catch {
      cost = 0; // costs endpoint is optional; ignore failures like the Python port
    }

    const { input, output } = sumTokens(completions.json);
    return [tokensRow(input + output), costRow(cost)];
  },
};
