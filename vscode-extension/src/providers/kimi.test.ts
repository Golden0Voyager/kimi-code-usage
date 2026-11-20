import { describe, it, expect, vi } from 'vitest';

vi.mock('../api', () => ({
  fetchUsage: vi.fn(() => Promise.resolve({ raw: true })),
  parsePayload: vi.fn(() => [{ label: 'Weekly' }]),
}));

import { fetchUsage, parsePayload } from '../api';
import { kimiProvider } from './kimi';

describe('kimi provider adapter', () => {
  it('fetches via fetchUsage and maps via parsePayload', async () => {
    const items = await kimiProvider.fetch('sk-key', 'https://api.kimi.com/coding/v1');
    expect(fetchUsage).toHaveBeenCalledWith('https://api.kimi.com/coding/v1', 'sk-key');
    expect(parsePayload).toHaveBeenCalledWith({ raw: true });
    expect(items).toEqual([{ label: 'Weekly' }]);
  });

  it('exposes the expected spec', () => {
    expect(kimiProvider.spec).toEqual({
      id: 'kimi',
      displayName: 'Kimi Code',
      keyEnv: 'KIMI_API_KEY',
      baseUrlEnv: 'KIMI_BASE_URL',
      defaultBaseUrl: 'https://api.kimi.com/coding/v1',
      windows: ['weekly', 'fiveHours', 'monthly'],
    });
  });
});
