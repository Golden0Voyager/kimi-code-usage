import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as https from 'https';

vi.mock('https', () => ({ get: vi.fn() }));

vi.mock('../i18n', () => ({
  t: (msg: string, ...args: unknown[]) => msg.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? '')),
}));

import { baseUrlV1, moneyRow, openrouterProvider, rateLimitText, usageText } from './openrouter';

const KEY = 'sk-or-test';
const BASE = 'https://openrouter.ai/api';
const KEY_URL = `${BASE}/v1/auth/key`;
const CREDITS_URL = `${BASE}/v1/credits`;

let routes: Record<string, { status: number; body: string }>;

function installRoutes() {
  vi.mocked(https.get).mockImplementation((url: unknown, _opts: unknown, cb: (r: unknown) => void) => {
    const r = routes[String(url)] ?? { status: 500, body: 'unrouted' };
    cb({
      statusCode: r.status,
      on: (event: string, fn: (chunk?: string) => void) => {
        if (event === 'data') fn(r.body);
        if (event === 'end') fn();
      },
    });
    return { on: vi.fn(), destroy: vi.fn() } as unknown as ReturnType<typeof https.get>;
  });
}

const fullKeyData = {
  data: {
    usage: 2.5,
    limit: 10,
    label: 'my-key-...1234',
    is_free_tier: false,
    limit_reset: 'Daily',
    expires_at: '2027-01-01',
    rate_limit: { requests: 20, interval: 's' },
    usage_daily: 1.25,
    usage_weekly: 2.5,
    usage_monthly: 3.75,
  },
};

describe('baseUrlV1', () => {
  it('appends /v1 when missing and strips trailing slashes', () => {
    expect(baseUrlV1('https://openrouter.ai/api')).toBe('https://openrouter.ai/api/v1');
    expect(baseUrlV1('https://openrouter.ai/api/')).toBe('https://openrouter.ai/api/v1');
    expect(baseUrlV1('https://proxy.local/v1')).toBe('https://proxy.local/v1');
  });
});

describe('moneyRow', () => {
  it('computes remaining and percent when limit is positive', () => {
    const row = moneyRow('Credits', 30, 100);
    expect(row.remaining).toBe(70);
    expect(row.percent_left).toBe(70);
    expect(row.text_value).toBeUndefined();
  });

  it('falls back to a literal text value when limit is null', () => {
    const row = moneyRow('Credits', 12.345, null);
    expect(row.text_value).toBe('$12.35 used');
    expect(row.percent_left).toBe(0);
  });
});

describe('rateLimitText', () => {
  it('renders unlimited and limited forms', () => {
    expect(rateLimitText(-1, 's')).toBe('Unlimited/s');
    expect(rateLimitText(20, 's')).toBe('20 req/s');
  });

  it('returns empty string when fields are missing', () => {
    expect(rateLimitText(null, 's')).toBe('');
    expect(rateLimitText(20, null)).toBe('');
  });
});

describe('usageText', () => {
  it('formats daily/weekly/monthly with null defaults', () => {
    expect(usageText(1.25, null, 3.75)).toBe('Daily: $1.2500 | Weekly: $0.0000 | Monthly: $3.7500');
    expect(usageText('abc', 0, 0)).toBe('Daily: $0.0000 | Weekly: $0.0000 | Monthly: $0.0000');
  });
});

describe('openrouterProvider.fetch', () => {
  beforeEach(() => {
    vi.mocked(https.get).mockReset();
    routes = {};
    installRoutes();
  });

  it('maps credits and key data to rows in order', async () => {
    routes[KEY_URL] = { status: 200, body: JSON.stringify(fullKeyData) };
    routes[CREDITS_URL] = {
      status: 200,
      body: JSON.stringify({ data: { total_credits: 100, total_usage: 30 } }),
    };

    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.map((r) => r.label)).toEqual([
      'Credits',
      'Key Usage',
      'Key Name',
      'Free Tier',
      'Limit Reset',
      'Expires At',
      'Rate Limit',
      'Usage',
    ]);
    const credits = rows[0]!;
    expect(credits.remaining).toBe(70);
    expect(credits.percent_left).toBe(70);
    expect(rows[1]!.remaining).toBe(7.5);
    expect(rows[2]!.text_value).toBe('my-key-*********1234');
    expect(rows[3]!.text_value).toBe('No');
    expect(rows[4]!.text_value).toBe('Daily');
    expect(rows[5]!.text_value).toBe('2027-01-01');
    expect(rows[6]!.text_value).toBe('20 req/s');
    expect(rows[7]!.text_value).toBe('Daily: $1.2500 | Weekly: $2.5000 | Monthly: $3.7500');
  });

  it('throws with the API error when auth/key is non-200', async () => {
    routes[KEY_URL] = { status: 401, body: 'invalid key' };
    await expect(openrouterProvider.fetch(KEY, BASE)).rejects.toThrow(
      'OpenRouter API Error HTTP 401: invalid key',
    );
  });

  it('throws on invalid JSON from auth/key', async () => {
    routes[KEY_URL] = { status: 200, body: 'not json' };
    await expect(openrouterProvider.fetch(KEY, BASE)).rejects.toThrow('Invalid JSON response');
  });

  it('tolerates an empty auth/key body', async () => {
    routes[KEY_URL] = { status: 200, body: '' };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows[0]!.text_value).toBe('$0.00 used');
  });

  it('falls back to a single Credits row when credits is non-200', async () => {
    routes[KEY_URL] = { status: 200, body: JSON.stringify(fullKeyData) };
    routes[CREDITS_URL] = { status: 402, body: 'no credits' };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.map((r) => r.label)).toEqual([
      'Credits',
      'Key Name',
      'Free Tier',
      'Limit Reset',
      'Expires At',
      'Rate Limit',
      'Usage',
    ]);
  });

  it('ignores credits on network error', async () => {
    routes[KEY_URL] = { status: 200, body: JSON.stringify(fullKeyData) };
    vi.mocked(https.get).mockImplementation((url: unknown, _opts: unknown, cb: (r: unknown) => void) => {
      if (String(url) === CREDITS_URL) {
        return {
          on: vi.fn((event: string, fn: () => void) => {
            if (event === 'error') fn();
          }),
          destroy: vi.fn(),
        } as unknown as ReturnType<typeof https.get>;
      }
      const r = routes[String(url)]!;
      cb({
        statusCode: r.status,
        on: (event: string, fn: (chunk?: string) => void) => {
          if (event === 'data') fn(r.body);
          if (event === 'end') fn();
        },
      });
      return { on: vi.fn(), destroy: vi.fn() } as unknown as ReturnType<typeof https.get>;
    });
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows[0]!.label).toBe('Credits');
    expect(rows[0]!.remaining).toBe(7.5);
  });

  it('labels a management key and masks ellipses', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({
        data: { usage: 1, limit: null, label: 'mgmt...key', is_management_key: true },
      }),
    };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows[0]!.text_value).toBe('$1.00 used');
    const nameRow = rows.find((r) => r.label === 'Management Key');
    expect(nameRow?.text_value).toBe('mgmt*********key');
  });

  it('renders an unlimited rate limit and Yes for free tier', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({
        data: { usage: 0, limit: null, is_free_tier: true, rate_limit: { requests: -1, interval: 'm' } },
      }),
    };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Rate Limit')?.text_value).toBe('Unlimited/m');
    expect(rows.find((r) => r.label === 'Free Tier')?.text_value).toBe('Yes');
  });

  it('ignores rate_limit with non-object shapes', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({ data: { usage: 0, limit: null, rate_limit: '20/s' } }),
    };
    let rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Rate Limit')).toBeUndefined();

    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({ data: { usage: 0, limit: null, rate_limit: [20, 's'] } }),
    };
    rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Rate Limit')).toBeUndefined();
  });

  it('falls back to a single Credits row when credits data is not an object', async () => {
    routes[KEY_URL] = { status: 200, body: JSON.stringify(fullKeyData) };
    routes[CREDITS_URL] = { status: 200, body: JSON.stringify({ data: 'nope' }) };
    let rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows[0]!.label).toBe('Credits');
    expect(rows[1]!.label).not.toBe('Key Usage');

    routes[CREDITS_URL] = { status: 200, body: JSON.stringify({ data: [1, 2] }) };
    rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.filter((r) => r.label === 'Credits')).toHaveLength(1);
  });

  it('ignores key labels that are empty or non-string', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({ data: { usage: 0, limit: null, label: '' } }),
    };
    let rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Key Name')).toBeUndefined();

    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({ data: { usage: 0, limit: null, label: 42 } }),
    };
    rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Key Name')).toBeUndefined();
  });

  it('keeps key labels without ellipses as-is', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({ data: { usage: 0, limit: null, label: 'prod-key' } }),
    };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Key Name')?.text_value).toBe('prod-key');
  });

  it('omits the rate limit row when requests or interval is null', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: JSON.stringify({
        data: { usage: 0, limit: null, rate_limit: { requests: null, interval: 's' } },
      }),
    };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Rate Limit')).toBeUndefined();
  });

  it('omits optional rows when fields are absent', async () => {
    routes[KEY_URL] = { status: 200, body: JSON.stringify({ data: { usage: 0, limit: null } }) };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.map((r) => r.label)).toEqual(['Credits', 'Usage']);
  });
});

describe('free-model daily quota row', () => {
  beforeEach(() => {
    vi.mocked(https.get).mockReset();
    routes = {};
    installRoutes();
  });

  const keyBodyWithFree = (free: unknown) =>
    JSON.stringify({
      data: { usage: 0, limit: null, free_model_daily_requests: free },
    });

  it('renders remaining/limit with the UTC reset note', async () => {
    routes[KEY_URL] = {
      status: 200,
      body: keyBodyWithFree({ used: 321, limit: 1000, remaining: 679 }),
    };
    const rows = await openrouterProvider.fetch(KEY, BASE);
    const row = rows.find((r) => r.label === 'Free Models');
    expect(row?.text_value).toBe('679/1000 free requests left today (resets at UTC 0)');
  });

  it('computes remaining when absent and clamps at zero', async () => {
    routes[KEY_URL] = { status: 200, body: keyBodyWithFree({ used: 40, limit: 50 }) };
    let rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Free Models')?.text_value).toContain('10/50');

    routes[KEY_URL] = { status: 200, body: keyBodyWithFree({ used: 1008, limit: 1000 }) };
    rows = await openrouterProvider.fetch(KEY, BASE);
    expect(rows.find((r) => r.label === 'Free Models')?.text_value).toContain('0/1000');
  });

  it.each([null, '1000', [1, 2], { used: 10 }, { limit: 1000 }, { used: 'x', limit: 1000 }])(
    'omits the row for unusable data: %j',
    async (free) => {
      routes[KEY_URL] = { status: 200, body: keyBodyWithFree(free) };
      const rows = await openrouterProvider.fetch(KEY, BASE);
      expect(rows.find((r) => r.label === 'Free Models')).toBeUndefined();
    },
  );
});
