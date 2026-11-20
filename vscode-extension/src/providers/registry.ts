import type { ProviderAdapter, ProviderId } from './types';
import { kimiProvider } from './kimi';
import { openrouterProvider } from './openrouter';
import { anthropicProvider } from './anthropic';
import { openaiProvider } from './openai';

export const PROVIDER_IDS: readonly ProviderId[] = ['kimi', 'openrouter', 'anthropic', 'openai'];

const PROVIDERS: ReadonlyMap<ProviderId, ProviderAdapter> = new Map(
  PROVIDER_IDS.map((id) => [id, providerFor(id)]),
);

function providerFor(id: ProviderId): ProviderAdapter {
  switch (id) {
    case 'kimi':
      return kimiProvider;
    case 'openrouter':
      return openrouterProvider;
    case 'anthropic':
      return anthropicProvider;
    case 'openai':
      return openaiProvider;
  }
}

export function getProvider(id: ProviderId): ProviderAdapter {
  return PROVIDERS.get(id) as ProviderAdapter;
}

export function listProviders(): ProviderAdapter[] {
  return PROVIDER_IDS.map((id) => getProvider(id));
}

export function isProviderId(v: unknown): v is ProviderId {
  return typeof v === 'string' && (PROVIDER_IDS as readonly string[]).includes(v);
}
