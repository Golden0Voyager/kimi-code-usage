import type { UsageItem } from '../types';
import { fetchUsage, parsePayload } from '../api';
import type { ProviderAdapter, ProviderSpec } from './types';

const SPEC: ProviderSpec = {
  id: 'kimi',
  displayName: 'Kimi Code',
  keyEnv: 'KIMI_API_KEY',
  baseUrlEnv: 'KIMI_BASE_URL',
  defaultBaseUrl: 'https://api.kimi.com/coding/v1',
  windows: ['weekly', 'fiveHours', 'monthly'],
};

/** Wraps the existing Kimi transport and parser without changing their signatures. */
export const kimiProvider: ProviderAdapter = {
  spec: SPEC,
  async fetch(apiKey: string, baseUrl: string): Promise<UsageItem[]> {
    const payload = await fetchUsage(baseUrl, apiKey);
    return parsePayload(payload);
  },
};
