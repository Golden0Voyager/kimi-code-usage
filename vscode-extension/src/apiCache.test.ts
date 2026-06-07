import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as api from './api';
import { clearCache, fetchUsageCached, cacheStats, setCacheTtlSeconds } from './apiCache';

const fakePayload = { usage: { used: 10, limit: 100 } };

beforeEach(() => {
  clearCache();
  vi.restoreAllMocks();
  setCacheTtlSeconds(60);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('fetchUsageCached', () => {
  it('returns fresh payload and fromCache=false on first call', async () => {
    const spy = vi.spyOn(api, 'fetchUsage').mockResolvedValue(fakePayload);
    const result = await fetchUsageCached('https://api.example.com', 'key-abcdef-123456');
    expect(result.payload).toBe(fakePayload);
    expect(result.fromCache).toBe(false);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('returns cached payload within TTL', async () => {
    const spy = vi.spyOn(api, 'fetchUsage').mockResolvedValue(fakePayload);
    await fetchUsageCached('https://api.example.com', 'k1');
    const second = await fetchUsageCached('https://api.example.com', 'k1');
    expect(second.fromCache).toBe(true);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('refetches after TTL expires', async () => {
    vi.useFakeTimers();
    const spy = vi.spyOn(api, 'fetchUsage').mockResolvedValue(fakePayload);
    await fetchUsageCached('https://api.example.com', 'k1');
    vi.advanceTimersByTime(61_000);
    const second = await fetchUsageCached('https://api.example.com', 'k1');
    expect(second.fromCache).toBe(false);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('clearCache forces refetch', async () => {
    const spy = vi.spyOn(api, 'fetchUsage').mockResolvedValue(fakePayload);
    await fetchUsageCached('https://api.example.com', 'k1');
    clearCache();
    await fetchUsageCached('https://api.example.com', 'k1');
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('coalesces concurrent requests for the same credentials', async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    const spy = vi.spyOn(api, 'fetchUsage').mockReturnValue(pending);

    const first = fetchUsageCached('https://api.example.com', 'k1');
    const second = fetchUsageCached('https://api.example.com', 'k1');
    expect(spy).toHaveBeenCalledTimes(1);

    resolveFetch(fakePayload);
    await expect(first).resolves.toEqual({ payload: fakePayload, fromCache: false });
    await expect(second).resolves.toEqual({ payload: fakePayload, fromCache: false });
  });
});

describe('cacheStats', () => {
  it('reports hasEntry=false when empty', () => {
    const stats = cacheStats();
    expect(stats.hasEntry).toBe(false);
  });

  it('reports hasEntry=true after fetch', async () => {
    vi.spyOn(api, 'fetchUsage').mockResolvedValue(fakePayload);
    await fetchUsageCached('https://api.example.com', 'k1');
    const stats = cacheStats();
    expect(stats.hasEntry).toBe(true);
  });
});
