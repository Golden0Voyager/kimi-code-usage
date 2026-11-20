import type { UsageItem } from '../types';

export type ProviderId = 'kimi' | 'openrouter' | 'anthropic' | 'openai';

export interface ProviderSpec {
  id: ProviderId;
  /** Human-readable name shown in the status bar and details. */
  displayName: string;
  /** Environment variable fallback for the API key. */
  keyEnv: string;
  /** Environment variable fallback for the base URL. */
  baseUrlEnv: string;
  defaultBaseUrl: string;
  /** Windows this provider can report; pace/predict only look at these. */
  windows: readonly ('weekly' | 'fiveHours' | 'monthly' | 'other')[];
}

export interface ProviderAdapter {
  spec: ProviderSpec;
  /** Fetch and map to UsageItem[]. Non-2xx on a required endpoint throws. */
  fetch(apiKey: string, baseUrl: string): Promise<UsageItem[]>;
}
