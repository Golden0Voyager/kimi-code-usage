import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as https from 'https';

vi.mock('https', () => ({ get: vi.fn() }));

import { baseUrlV1, monthWindow, OPENAI_ORG_KEY_HINT, openaiProvider } from './openai';

const COMPLETIONS =
  'https://api.openai.com/v1/organization/usage/completions?start_time=2026-11-01&end_time=2026-11-21';
const COSTS = 'https://api.openai.com/v1/organization/usage/costs?start_time=2026-11-01&end_time=2026-11-21';

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

describe('monthWindow', () => {
  it('covers the first of the month through tomorrow', () => {
    const { start, end } = monthWindow(new Date(2026, 10, 20, 12, 0, 0));
    expect(start).toBe('2026-11-01');
    expect(end).toBe('2026-11-21');
  });
});

describe('baseUrlV1', () => {
  it('keeps /v1 when present and inserts it otherwise', () => {
    expect(baseUrlV1('https://api.openai.com')).toBe('https://api.openai.com/v1');
    expect(baseUrlV1('https://proxy.local/v1/')).toBe('https://proxy.local/v1');
  });
});

describe('openaiProvider.fetch', () => {
  beforeEach(() => {
    vi.mocked(https.get).mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 20, 12, 0, 0));
    routes = {};
    installRoutes();
  });

  it('sums completion tokens and costs into Tokens and Cost rows', async () => {
    routes[COMPLETIONS] = {
      status: 200,
      body: JSON.stringify({
        data: [
          { input_tokens: 100, output_tokens: 50 },
          { input_tokens: 25, output_tokens: 5 },
          { input_tokens: 'not-a-number' },
        ],
      }),
    };
    routes[COSTS] = {
      status: 200,
      body: JSON.stringify({
        data: [{ amount: { value: 1.5 } }, { amount: { value: 0.25 } }, { amount: {} }],
      }),
    };

    const rows = await openaiProvider.fetch('sk-admin', 'https://api.openai.com');
    expect(rows[0]!.label).toBe('Tokens');
    expect(rows[0]!.used).toBe(180);
    expect(rows[0]!.text_value).toBe('180 tokens');
    expect(rows[1]!.label).toBe('Cost');
    expect(rows[1]!.used).toBe(1.75);
  });

  it('skips malformed buckets and cost items', async () => {
    routes[COMPLETIONS] = {
      status: 200,
      body: JSON.stringify({ data: [null, 'str', 42, { input_tokens: 7, output_tokens: 3 }] }),
    };
    routes[COSTS] = {
      status: 200,
      body: JSON.stringify({
        data: [null, 'x', { amount: 'str' }, { amount: [1] }, { amount: {} }, { amount: { value: 2 } }],
      }),
    };
    const rows = await openaiProvider.fetch('sk-admin', 'https://api.openai.com');
    expect(rows[0]!.used).toBe(10);
    expect(rows[1]!.used).toBe(2);
  });

  it('treats invalid JSON completions as zero usage', async () => {
    routes[COMPLETIONS] = { status: 200, body: 'not json' };
    routes[COSTS] = { status: 200, body: JSON.stringify({ data: [] }) };
    const rows = await openaiProvider.fetch('sk-admin', 'https://api.openai.com');
    expect(rows[0]!.used).toBe(0);
    expect(rows[1]!.used).toBe(0);
  });

  it('treats non-object JSON roots as zero usage', async () => {
    routes[COMPLETIONS] = { status: 200, body: '"just a string"' };
    routes[COSTS] = { status: 200, body: '"just a string"' };
    const rows = await openaiProvider.fetch('sk-admin', 'https://api.openai.com');
    expect(rows[0]!.used).toBe(0);
    expect(rows[1]!.used).toBe(0);
  });

  it('throws the Org Admin hint on 401/403', async () => {
    routes[COMPLETIONS] = { status: 401, body: 'nope' };
    await expect(openaiProvider.fetch('sk-proj', 'https://api.openai.com')).rejects.toThrow(
      OPENAI_ORG_KEY_HINT,
    );
  });

  it('throws on other non-2xx statuses', async () => {
    routes[COMPLETIONS] = { status: 500, body: 'broken' };
    await expect(openaiProvider.fetch('sk-admin', 'https://api.openai.com')).rejects.toThrow(
      'OpenAI API Error HTTP 500: broken',
    );
  });

  it('keeps cost at 0 when the costs endpoint fails', async () => {
    routes[COMPLETIONS] = { status: 200, body: JSON.stringify({ data: [] }) };
    routes[COSTS] = { status: 500, body: 'nope' };
    const rows = await openaiProvider.fetch('sk-admin', 'https://api.openai.com');
    expect(rows[1]!.used).toBe(0);
    expect(rows[0]!.used).toBe(0);
  });

  it('ignores costs on network error', async () => {
    routes[COMPLETIONS] = { status: 200, body: JSON.stringify({ data: [] }) };
    vi.mocked(https.get).mockImplementation((url: unknown, _opts: unknown, cb: (r: unknown) => void) => {
      if (String(url) === COSTS) {
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
    const rows = await openaiProvider.fetch('sk-admin', 'https://api.openai.com');
    expect(rows[1]!.used).toBe(0);
  });
});
