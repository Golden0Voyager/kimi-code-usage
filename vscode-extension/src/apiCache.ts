import { fetchUsage } from './api';
import { DEFAULT_API_CACHE_TTL_SECONDS } from './types';

interface CacheEntry {
  expiresAt: number;
  payload: unknown;
}

const cache = new Map<string, CacheEntry>();
const inFlight = new Map<string, Promise<unknown>>();
let ttlMs = DEFAULT_API_CACHE_TTL_SECONDS * 1000;
let cacheGeneration = 0;

export function setCacheTtlSeconds(seconds: number): void {
  ttlMs = Math.max(0, seconds) * 1000;
}

export function clearCache(): void {
  cache.clear();
  inFlight.clear();
  cacheGeneration++;
}

export function cacheStats(): { hasEntry: boolean; ageMs: number | null; ttlMs: number } {
  if (cache.size === 0) return { hasEntry: false, ageMs: null, ttlMs };
  const first = cache.values().next().value as CacheEntry;
  return { hasEntry: true, ageMs: Date.now() - (first.expiresAt - ttlMs), ttlMs };
}

function keyFor(baseUrl: string, apiKey: string): string {
  return `${baseUrl}::${apiKey.slice(0, 6)}::${apiKey.length}`;
}

export async function fetchUsageCached(
  baseUrl: string,
  apiKey: string,
): Promise<{ payload: unknown; fromCache: boolean }> {
  const key = keyFor(baseUrl, apiKey);
  const entry = cache.get(key);
  if (entry && entry.expiresAt > Date.now()) {
    return { payload: entry.payload, fromCache: true };
  }
  const pending = inFlight.get(key);
  if (pending) {
    return { payload: await pending, fromCache: false };
  }

  const generation = cacheGeneration;
  const request = fetchUsage(baseUrl, apiKey)
    .then((payload) => {
      if (generation === cacheGeneration) {
        cache.set(key, { expiresAt: Date.now() + ttlMs, payload });
      }
      return payload;
    })
    .finally(() => {
      inFlight.delete(key);
    });
  inFlight.set(key, request);
  const payload = await request;
  return { payload, fromCache: false };
}
