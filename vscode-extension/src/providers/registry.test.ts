import { describe, it, expect } from 'vitest';
import { getProvider, listProviders, isProviderId, PROVIDER_IDS } from './registry';

describe('registry', () => {
  it('returns an adapter whose spec.id matches for every known id', () => {
    for (const id of PROVIDER_IDS) {
      expect(getProvider(id).spec.id).toBe(id);
    }
  });

  it('listProviders returns all providers in PROVIDER_IDS order', () => {
    const ids = listProviders().map((p) => p.spec.id);
    expect(ids).toEqual([...PROVIDER_IDS]);
  });

  it('isProviderId narrows valid ids and rejects anything else', () => {
    expect(isProviderId('openrouter')).toBe(true);
    expect(isProviderId('kimi')).toBe(true);
    expect(isProviderId('bogus')).toBe(false);
    expect(isProviderId(42)).toBe(false);
    expect(isProviderId(null)).toBe(false);
    expect(isProviderId(undefined)).toBe(false);
  });
});
