import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as https from 'https';

vi.mock('https', () => ({ get: vi.fn() }));

import { ANTHROPIC_UNREADABLE_KEY_HINT, anthropicProvider } from './anthropic';

function route(status: number, body: string) {
  vi.mocked(https.get).mockImplementation((_url: unknown, _opts: unknown, cb: (r: unknown) => void) => {
    cb({
      statusCode: status,
      on: (event: string, fn: (chunk?: string) => void) => {
        if (event === 'data') fn(body);
        if (event === 'end') fn();
      },
    });
    return { on: vi.fn(), destroy: vi.fn() } as unknown as ReturnType<typeof https.get>;
  });
}

describe('anthropicProvider.fetch', () => {
  beforeEach(() => {
    vi.mocked(https.get).mockReset();
  });

  it('maps five_hour/seven_day utilization to 5 Hours and 7 Days rows', async () => {
    route(200, JSON.stringify({ five_hour: { utilization: 0.6 }, seven_day: { utilization: 0.25 } }));
    const rows = await anthropicProvider.fetch('token', 'https://api.anthropic.com/');
    expect(rows).toHaveLength(2);
    expect(rows[0]!.label).toBe('5 Hours');
    expect(rows[0]!.used).toBe(60);
    expect(rows[0]!.percent_left).toBe(40);
    expect(rows[1]!.label).toBe('7 Days');
    expect(rows[1]!.percent_left).toBe(75);
  });

  it('clamps utilization above 1.0', async () => {
    route(200, JSON.stringify({ five_hour: { utilization: 1.4 } }));
    const rows = await anthropicProvider.fetch('token', 'https://api.anthropic.com');
    expect(rows[0]!.percent_left).toBe(0);
  });

  it('returns the hint row on 401', async () => {
    route(401, '{}');
    const rows = await anthropicProvider.fetch('sk-ant-key', 'https://api.anthropic.com');
    expect(rows).toHaveLength(1);
    expect(rows[0]!.label).toBe('API Plan');
    expect(rows[0]!.text_value).toBe(ANTHROPIC_UNREADABLE_KEY_HINT);
  });

  it('returns the hint row on 403', async () => {
    route(403, '{}');
    const rows = await anthropicProvider.fetch('sk-ant-key', 'https://api.anthropic.com');
    expect(rows[0]!.text_value).toBe(ANTHROPIC_UNREADABLE_KEY_HINT);
  });

  it('throws on other non-2xx statuses', async () => {
    route(500, 'boom');
    await expect(anthropicProvider.fetch('token', 'https://api.anthropic.com')).rejects.toThrow(
      'Anthropic API Error HTTP 500: boom',
    );
  });

  it('treats missing or invalid JSON windows as 0% used', async () => {
    route(200, 'not json');
    const rows = await anthropicProvider.fetch('token', 'https://api.anthropic.com');
    expect(rows[0]!.percent_left).toBe(100);
    expect(rows[1]!.percent_left).toBe(100);
  });

  it('treats a non-numeric utilization as 0', async () => {
    route(200, JSON.stringify({ five_hour: { utilization: 'abc' } }));
    const rows = await anthropicProvider.fetch('token', 'https://api.anthropic.com');
    expect(rows[0]!.percent_left).toBe(100);
  });
});
