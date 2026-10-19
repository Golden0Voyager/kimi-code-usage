import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as https from 'https';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

vi.mock('https', () => ({
  get: vi.fn(),
}));
import {
  detectWindowType,
  getWindowSeconds,
  parsePayload,
  toInt,
  formatDuration,
  normalizeIso,
  formatResetTimeAbsolute,
  isLinkIssue,
  fetchUsage,
  setUserAgentVersion,
  localizedLimitName,
  shortLabel,
  findWindowItem,
  isLowRemaining,
  formatResetTime,
  secondsUntil,
  readKimiCliAccessToken,
  fetchMonthlyUsageViaOAuth,
} from './api';
import { setTranslator, type Translator } from './i18n';

const noopTranslator = {
  t: (m: string, ...args: unknown[]) => m.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? '')),
} as unknown as Translator;
beforeEach(() => setTranslator(noopTranslator));
afterEach(() => {
  vi.useRealTimers();
  setTranslator(undefined as unknown as Translator);
});

describe('detectWindowType', () => {
  it('detects weekly', () => {
    expect(detectWindowType('Weekly limit')).toBe('weekly');
    expect(detectWindowType('weekly_quota')).toBe('weekly');
    expect(detectWindowType('\u5468\u9650\u989D')).toBe('weekly');
  });
  it('detects five hours', () => {
    expect(detectWindowType('5h rolling')).toBe('fiveHours');
    expect(detectWindowType('5 hour window')).toBe('fiveHours');
    expect(detectWindowType('5-hour rolling')).toBe('fiveHours');
    expect(detectWindowType('5hr window')).toBe('fiveHours');
    expect(detectWindowType('5 hours')).toBe('fiveHours');
    expect(detectWindowType('5h')).toBe('fiveHours');
    expect(detectWindowType('5\u5C0F\u65F6\u9650\u989D')).toBe('fiveHours');
  });
  it('detects monthly', () => {
    expect(detectWindowType('Monthly plan')).toBe('monthly');
    expect(detectWindowType('monthly_quota')).toBe('monthly');
  });
  it('falls back to other', () => {
    expect(detectWindowType('Custom window')).toBe('other');
    expect(detectWindowType('')).toBe('other');
  });
});

describe('getWindowSeconds', () => {
  it('returns 5h for five hours label', () => {
    expect(getWindowSeconds('5h limit')).toBe(5 * 3600);
  });
  it('returns 30d for monthly label', () => {
    expect(getWindowSeconds('Monthly plan')).toBe(30 * 24 * 3600);
  });
  it('returns 7d default', () => {
    expect(getWindowSeconds('Weekly limit')).toBe(7 * 24 * 3600);
    expect(getWindowSeconds('Unknown')).toBe(7 * 24 * 3600);
  });
});

describe('parsePayload', () => {
  it('handles null limit with valid used', () => {
    const payload = { usage: { used: 30, limit: null, name: 'Test' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(30);
    expect(items[0].limit).toBe(0);
  });

  it('filters out usage entries with null used and limit', () => {
    const payload = { usage: { used: null, limit: null, name: 'Empty' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(0);
  });

  it('returns empty array for non-object payload', () => {
    expect(parsePayload(null)).toEqual([]);
    expect(parsePayload(undefined)).toEqual([]);
    expect(parsePayload('string')).toEqual([]);
  });

  it('parses usage block with used/limit/reset_in', () => {
    const payload = {
      usage: { used: 30, limit: 100, reset_in: 3600, name: 'Weekly limit' },
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(30);
    expect(items[0].limit).toBe(100);
    expect(items[0].percent_left).toBeCloseTo(70);
    expect(items[0].reset_seconds).toBe(3600);
  });

  it('skips zero reset_in value', () => {
    const payload = { usage: { used: 30, limit: 100, reset_in: 0, name: 'Weekly' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].reset_seconds).toBe(0);
  });

  it('skips null reset_in value', () => {
    const payload = { usage: { used: 30, limit: 100, reset_in: null, name: 'Weekly limit' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].reset_seconds).toBeNull();
  });

  it('infers used from remaining when used missing', () => {
    const payload = { usage: { remaining: 25, limit: 100, name: 'Weekly limit' } };
    const items = parsePayload(payload);
    expect(items[0].used).toBe(75);
  });

  it('handles null used with valid limit', () => {
    const payload = { usage: { limit: 100, name: 'Test' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(0);
    expect(items[0].limit).toBe(100);
    expect(items[0].percent_left).toBe(100);
  });

  it('handles zero limit without division by zero', () => {
    const payload = { usage: { used: 0, limit: 0, name: 'Empty' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].remaining).toBe(0);
    expect(items[0].percent_left).toBe(0);
  });

  it('clamps display remaining percent to 0-100 for out-of-range API values', () => {
    expect(parsePayload({ usage: { used: 120, limit: 100, name: 'Weekly limit' } })[0].percent_left).toBe(0);
    expect(
      parsePayload({ usage: { remaining: 150, limit: 100, name: 'Weekly limit' } })[0].percent_left,
    ).toBe(100);
  });

  it('parses limits array with detail block', () => {
    const payload = {
      limits: [
        {
          name: 'Weekly limit',
          detail: { used: 10, limit: 100, reset_in: 7200 },
        },
      ],
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Weekly limit');
    expect(items[0].used).toBe(10);
    expect(items[0].reset_seconds).toBe(7200);
  });

  it('skips reset_at with invalid timestamp', () => {
    const payload = { usage: { used: 0, limit: 100, reset_at: 'not-a-date', name: 'Test' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].reset_seconds).toBeNull();
  });

  it('skips reset_at with past timestamp', () => {
    const past = new Date(Date.now() - 3600000).toISOString();
    const payload = { usage: { used: 0, limit: 100, reset_at: past, name: 'Test' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].reset_seconds).toBeNull();
  });

  it('derives reset_seconds from reset_at when reset_in missing', () => {
    const future = new Date(Date.now() + 60_000).toISOString();
    const payload = { usage: { used: 0, limit: 100, reset_at: future, name: 'Weekly limit' } };
    const items = parsePayload(payload);
    expect(items[0].reset_seconds).not.toBeNull();
    expect(items[0].reset_seconds!).toBeGreaterThan(50);
  });

  it('falls back to detail name when item name is missing', () => {
    const payload = {
      limits: [
        {
          name: null,
          detail: { name: 'Fallback Name', used: 5, limit: 10 },
        },
      ],
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Fallback Name');
  });

  it('skips non-object entries in limits array', () => {
    const payload = { limits: [null, undefined, { detail: { used: 5, limit: 10 } }] };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
  });

  it('skips limits entries without usable data', () => {
    const payload = { limits: [{}, { detail: { used: 5, limit: 10 } }] };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(5);
  });

  it('falls back to generic seconds label for unknown timeUnit', () => {
    const raw = {
      limits: [{ detail: { used: 5, limit: 100 }, window: { timeUnit: 'SECOND', duration: 30 } }] as any,
    };
    const result = parsePayload(raw);
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('30s limit');
  });

  it('formats MINUTE timeUnit as hours when duration >= 60 and divisible by 60', () => {
    const raw = {
      limits: [{ detail: { used: 10, limit: 100 }, window: { timeUnit: 'MINUTE', duration: 120 } }] as any,
    };
    const result = parsePayload(raw);
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('2h limit');
  });

  it('formats DAY timeUnit label', () => {
    const raw = {
      limits: [{ detail: { used: 10, limit: 100 }, window: { timeUnit: 'DAY', duration: 14 } }] as any,
    };
    const result = parsePayload(raw);
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('14d limit');
  });

  it('formats HOUR timeUnit label', () => {
    const raw = {
      limits: [{ detail: { used: 10, limit: 100 }, window: { timeUnit: 'HOUR', duration: 3 } }] as any,
    };
    const result = parsePayload(raw);
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('3h limit');
  });

  it('formats sub-hour MINUTE duration as minutes', () => {
    const raw = {
      limits: [{ detail: { used: 5, limit: 100 }, window: { timeUnit: 'MINUTE', duration: 30 } }] as any,
    };
    const result = parsePayload(raw);
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('30m limit');
  });

  it('formats MINUTE timeUnit as minutes when not divisible by 60', () => {
    const raw = {
      limits: [{ detail: { used: 10, limit: 100 }, window: { timeUnit: 'MINUTE', duration: 90 } }] as any,
    };
    const result = parsePayload(raw);
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('90m limit');
  });
});

describe('parsePayload parallel / boosterWallet / totalQuota', () => {
  it('parses the legacy 2026-08-28 camelCase shape', () => {
    const payload = {
      usage: { limit: '100', used: '67', remaining: '33', resetTime: '2026-09-02T08:22:11.102028Z' },
      limits: [
        {
          window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' },
          detail: { limit: '100', used: '21', remaining: '79', resetTime: '2026-08-28T09:22:11.102028Z' },
        },
      ],
      parallel: { limit: '20' },
      totalQuota: {},
      boosterWallet: {
        status: 'STATUS_DISABLED',
        allowTopup: true,
        monthlyUsed: { currency: 'CNY', priceInCents: '0' },
        monthlyChargeLimit: { currency: 'CNY', priceInCents: '10000' },
      },
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(3);
    const parallel = items.find((i) => i.label === 'Parallel limit');
    expect(parallel).toBeDefined();
    expect(parallel!.used).toBe(0);
    expect(parallel!.limit).toBe(20);
    expect(parallel!.remaining).toBe(20);
    expect(parallel!.percent_left).toBe(100);
    expect(parallel!.reset_hint).toBeNull();
    expect(parallel!.reset_seconds).toBeNull();
    expect(parallel!.reset_at).toBeNull();
    expect(items.some((i) => i.label === 'Extra Usage')).toBe(false);
    expect(items.some((i) => i.label === 'Total quota')).toBe(false);
  });

  it('parses parallel limit as number', () => {
    const items = parsePayload({ parallel: { limit: 5 } });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Parallel limit');
    expect(items[0].limit).toBe(5);
  });

  it('skips parallel when missing, non-object, or limit not numeric', () => {
    expect(parsePayload({})).toHaveLength(0);
    expect(parsePayload({ parallel: null })).toHaveLength(0);
    expect(parsePayload({ parallel: 'nope' } as any)).toHaveLength(0);
    expect(parsePayload({ parallel: {} })).toHaveLength(0);
    expect(parsePayload({ parallel: { limit: 'abc' } })).toHaveLength(0);
  });

  it('clamps negative parallel limit to zero', () => {
    const items = parsePayload({ parallel: { limit: '-3' } });
    expect(items).toHaveLength(1);
    expect(items[0].limit).toBe(0);
  });

  it('parses enabled boosterWallet with string cents values', () => {
    const payload = {
      boosterWallet: {
        status: 'STATUS_ENABLED',
        monthlyUsed: { currency: 'CNY', priceInCents: '1234' },
        monthlyChargeLimit: { currency: 'CNY', priceInCents: '10000' },
      },
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Extra Usage');
    expect(items[0].used).toBeCloseTo(12.34);
    expect(items[0].limit).toBe(100);
    expect(items[0].remaining).toBeCloseTo(87.66);
    expect(items[0].percent_left).toBeCloseTo(87.66);
    expect(items[0].reset_at).toBeNull();
  });

  it('treats zero booster charge limit as unlimited', () => {
    const payload = {
      boosterWallet: {
        status: 'STATUS_ENABLED',
        monthlyUsed: { currency: 'CNY', priceInCents: '500' },
        monthlyChargeLimit: { currency: 'CNY', priceInCents: '0' },
      },
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].limit).toBe(0);
    expect(items[0].remaining).toBe(0);
    expect(items[0].percent_left).toBe(100);
  });

  it('clamps booster percent when used exceeds limit', () => {
    const payload = {
      boosterWallet: {
        status: 'STATUS_ENABLED',
        monthlyUsed: { priceInCents: 15000 },
        monthlyChargeLimit: { priceInCents: 10000 },
      },
    };
    const items = parsePayload(payload);
    expect(items[0].remaining).toBe(0);
    expect(items[0].percent_left).toBe(0);
  });

  it('skips boosterWallet when disabled', () => {
    const payload = {
      boosterWallet: {
        status: 'STATUS_DISABLED',
        monthlyUsed: { priceInCents: '500' },
        monthlyChargeLimit: { priceInCents: '10000' },
      },
    };
    expect(parsePayload(payload)).toHaveLength(0);
  });

  it('skips boosterWallet when missing, non-object, or both money fields missing', () => {
    expect(parsePayload({ boosterWallet: null })).toHaveLength(0);
    expect(parsePayload({ boosterWallet: 42 } as any)).toHaveLength(0);
    expect(parsePayload({ boosterWallet: { status: 'STATUS_ENABLED' } })).toHaveLength(0);
    expect(
      parsePayload({
        boosterWallet: {
          status: 'STATUS_ENABLED',
          monthlyUsed: { priceInCents: 'oops' },
          monthlyChargeLimit: 'not-an-object',
        },
      }),
    ).toHaveLength(0);
  });

  it('defaults missing booster used to 0 when charge limit present', () => {
    const payload = {
      boosterWallet: {
        status: 'STATUS_ENABLED',
        monthlyChargeLimit: { priceInCents: '10000' },
      },
    };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(0);
    expect(items[0].limit).toBe(100);
    expect(items[0].percent_left).toBe(100);
  });

  it('parses totalQuota with string values', () => {
    const payload = { totalQuota: { limit: '500', used: '125' } };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Total quota');
    expect(items[0].used).toBe(125);
    expect(items[0].limit).toBe(500);
    expect(items[0].percent_left).toBe(75);
  });

  it('skips empty or unusable totalQuota', () => {
    expect(parsePayload({ totalQuota: {} })).toHaveLength(0);
    expect(parsePayload({ totalQuota: null })).toHaveLength(0);
    expect(parsePayload({ totalQuota: 'x' } as any)).toHaveLength(0);
  });

  it('does not throw on hostile input', () => {
    expect(() =>
      parsePayload({
        usage: null,
        limits: 'not-an-array',
        parallel: { limit: { nested: true } },
        boosterWallet: { status: 'STATUS_ENABLED', monthlyUsed: [], monthlyChargeLimit: null },
        booster_wallet: 'not-an-object',
        totalQuota: [],
        usages: { limit_5h: { used_ratio: {} }, limit_7d: [] },
      } as any),
    ).not.toThrow();
  });
});

describe('parsePayload live 2026-10-19 shape (usages / booster_wallet)', () => {
  const LIVE = {
    usage: { limit: '100', used: '16', remaining: '84', resetTime: '2026-10-26T08:22:11.102028Z' },
    limits: [
      {
        window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' },
        detail: {
          limit: '100',
          used: '0',
          remaining: '100',
          resetTime: '2026-10-19T09:22:11.102028Z',
        },
      },
    ],
    usages: { limit_5h: { used_ratio: 0 }, limit_7d: { used_ratio: 0.1631 } },
    booster_wallet: {
      status: 'STATUS_DISABLED',
      allowTopup: true,
      monthlyUsed: { currency: 'CNY', priceInCents: '0' },
      monthlyChargeLimit: { currency: 'CNY', priceInCents: '10000' },
    },
  };

  it('replays the live payload without duplicate windows', () => {
    const items = parsePayload(LIVE);
    expect(items).toHaveLength(2);
    expect(items.filter((i) => detectWindowType(i.label) === 'weekly')).toHaveLength(1);
    expect(items.filter((i) => detectWindowType(i.label) === 'fiveHours')).toHaveLength(1);
    expect(items[0].label).toBe('Weekly limit');
    expect(items[0].used).toBe(16); // from `usage`, never from usages.limit_7d
  });

  it('reads snake_case booster_wallet with string cents', () => {
    const items = parsePayload({
      booster_wallet: {
        status: 'STATUS_ENABLED',
        monthlyUsed: { currency: 'CNY', priceInCents: '1234' },
        monthlyChargeLimit: { currency: 'CNY', priceInCents: '10000' },
      },
    });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Extra Usage');
    expect(items[0].used).toBeCloseTo(12.34);
    expect(items[0].limit).toBe(100);
    expect(items[0].percent_left).toBeCloseTo(87.66);
  });

  it('prefers snake_case and falls back to camelCase', () => {
    const snake = {
      status: 'STATUS_ENABLED',
      monthlyUsed: { priceInCents: '5000' },
      monthlyChargeLimit: { priceInCents: '10000' },
    };
    const camel = {
      status: 'STATUS_ENABLED',
      monthlyUsed: { priceInCents: '1' },
      monthlyChargeLimit: { priceInCents: '10000' },
    };
    expect(parsePayload({ booster_wallet: snake, boosterWallet: camel })[0].used).toBeCloseTo(50);
    expect(parsePayload({ booster_wallet: {}, boosterWallet: camel })[0].used).toBeCloseTo(0.01);
    expect(parsePayload({ boosterWallet: camel })[0].used).toBeCloseTo(0.01);
  });

  it('backfills the weekly row from usages.limit_7d when usage is absent', () => {
    const items = parsePayload({ usages: { limit_7d: { used_ratio: 0.1631 } } });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('Weekly limit');
    expect(items[0].used).toBeCloseTo(16.31);
    expect(items[0].limit).toBe(100);
    expect(items[0].remaining).toBeCloseTo(83.69);
    expect(items[0].percent_left).toBeCloseTo(83.69);
    expect(detectWindowType(items[0].label)).toBe('weekly');
  });

  it('backfills the 5h row from usages.limit_5h when no 300-minute row exists', () => {
    const items = parsePayload({ usages: { limit_5h: { used_ratio: 0.25 } } });
    expect(items).toHaveLength(1);
    expect(items[0].label).toBe('5 Hours');
    expect(items[0].used).toBe(25);
    expect(items[0].remaining).toBe(75);
    expect(items[0].percent_left).toBe(75);
    expect(detectWindowType(items[0].label)).toBe('fiveHours');
  });

  it('does not duplicate a 5h window that already produced a row', () => {
    const items = parsePayload({
      limits: [
        {
          window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' },
          detail: { limit: '100', used: '21' },
        },
      ],
      usages: { limit_5h: { used_ratio: 0.9 } },
    });
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(21);
  });

  it('counts rows emitted, not windows seen', () => {
    const items = parsePayload({
      limits: [{ window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' }, detail: {} }],
      usages: { limit_5h: { used_ratio: 0.5 } },
    });
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(50);
  });

  it('does not depend on the limits label to detect the 5h window', () => {
    const items = parsePayload({
      limits: [
        {
          window: { duration: 5, timeUnit: 'TIME_UNIT_HOUR' },
          detail: { name: '五小时限额', limit: '100', used: '21' },
        },
      ],
      usages: { limit_5h: { used_ratio: 0.9 } },
    });
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(21);
  });

  it('clamps out-of-range ratios and accepts numeric strings', () => {
    expect(parsePayload({ usages: { limit_5h: { used_ratio: 2.5 } } })[0].used).toBe(100);
    expect(parsePayload({ usages: { limit_5h: { used_ratio: -1 } } })[0].used).toBe(0);
    expect(parsePayload({ usages: { limit_7d: { used_ratio: '0.1631' } } })[0].used).toBeCloseTo(16.31);
  });

  it('skips unusable usages entries', () => {
    expect(parsePayload({ usages: 'nope' } as any)).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: 'x' } } as any)).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: null } } as any)).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: {} } })).toHaveLength(0);
    expect(parsePayload({ usages: { limit_7d: { used_ratio: 'abc' } } })).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: { used_ratio: true } } } as any)).toHaveLength(0);
    // A blank or non-decimal string must not fabricate a "0% used" row.
    expect(parsePayload({ usages: { limit_5h: { used_ratio: '' } } })).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: { used_ratio: '   ' } } })).toHaveLength(0);
    expect(parsePayload({ usages: { limit_5h: { used_ratio: '0x10' } } })).toHaveLength(0);
  });

  it('backfills 5h even when a different limit window was emitted', () => {
    const items = parsePayload({
      limits: [{ window: { duration: 7, timeUnit: 'TIME_UNIT_DAY' }, detail: { limit: '100', used: '40' } }],
      usages: { limit_5h: { used_ratio: 0.25 } },
    });
    expect(items).toHaveLength(2);
    expect(items[1].used).toBe(25);
  });

  it('ignores a name carried by the usages entry', () => {
    const items = parsePayload({ usages: { limit_7d: { used_ratio: 0.5, name: '7d' } } });
    expect(items[0].label).toBe('Weekly limit');
    expect(detectWindowType(items[0].label)).toBe('weekly');
  });

  it('leads with the backfilled weekly row', () => {
    const items = parsePayload({
      limits: [
        {
          window: { duration: 300, timeUnit: 'TIME_UNIT_MINUTE' },
          detail: { limit: '100', used: '21' },
        },
      ],
      usages: { limit_7d: { used_ratio: 0.5 } },
    });
    expect(items.map((i) => i.label)).toEqual(['Weekly limit', '5h limit']);
  });

  it('falls through a non-object snake_case wallet', () => {
    const items = parsePayload({
      booster_wallet: 'junk',
      boosterWallet: {
        status: 'STATUS_ENABLED',
        monthlyUsed: { priceInCents: '100' },
        monthlyChargeLimit: { priceInCents: '10000' },
      },
    } as any);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(1);
  });
});

describe('readKimiCliAccessToken', () => {
  it('returns the token for a valid, unexpired credential file', () => {
    const tmp = path.join(os.tmpdir(), `kimi-cred-valid-${Date.now()}-${Math.random()}.json`);
    fs.writeFileSync(
      tmp,
      JSON.stringify({
        access_token: 'valid-token',
        expires_at: Math.floor(Date.now() / 1000) + 3600,
      }),
    );
    try {
      expect(readKimiCliAccessToken(tmp)).toBe('valid-token');
    } finally {
      fs.unlinkSync(tmp);
    }
  });

  it('returns null when the token is expired (expires_at very small)', () => {
    const tmp = path.join(os.tmpdir(), `kimi-cred-expired-${Date.now()}-${Math.random()}.json`);
    fs.writeFileSync(
      tmp,
      JSON.stringify({
        access_token: 'valid-token',
        expires_at: 100,
      }),
    );
    try {
      expect(readKimiCliAccessToken(tmp)).toBeNull();
    } finally {
      fs.unlinkSync(tmp);
    }
  });

  it('returns null when the credential file does not exist', () => {
    expect(readKimiCliAccessToken('/nonexistent/path/kimi-code.json')).toBeNull();
  });

  it('returns null when access_token is missing or not a string', () => {
    const tmp = path.join(os.tmpdir(), `kimi-cred-bad-${Date.now()}-${Math.random()}.json`);
    fs.writeFileSync(tmp, JSON.stringify({ expires_at: Math.floor(Date.now() / 1000) + 3600 }));
    try {
      expect(readKimiCliAccessToken(tmp)).toBeNull();
    } finally {
      fs.unlinkSync(tmp);
    }

    const tmp2 = path.join(os.tmpdir(), `kimi-cred-bad2-${Date.now()}-${Math.random()}.json`);
    fs.writeFileSync(tmp2, JSON.stringify({ access_token: 12345 }));
    try {
      expect(readKimiCliAccessToken(tmp2)).toBeNull();
    } finally {
      fs.unlinkSync(tmp2);
    }
  });

  it('returns null when the file is not valid JSON', () => {
    const tmp = path.join(os.tmpdir(), `kimi-cred-json-${Date.now()}-${Math.random()}.json`);
    fs.writeFileSync(tmp, 'not-json{');
    try {
      expect(readKimiCliAccessToken(tmp)).toBeNull();
    } finally {
      fs.unlinkSync(tmp);
    }
  });
});

describe('fetchMonthlyUsageViaOAuth', () => {
  let mockReq: { on: any; destroy: any };
  let mockRes: { on: any; statusCode: number };

  const writeCred = (body: unknown): string => {
    const tmp = path.join(os.tmpdir(), `kimi-oauth-cred-${Date.now()}-${Math.random()}.json`);
    fs.writeFileSync(tmp, JSON.stringify(body));
    return tmp;
  };

  const validCredPath = (): string =>
    writeCred({
      access_token: 'oauth-token',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
    });

  beforeEach(() => {
    vi.mocked(https.get).mockReset();
    mockReq = { on: vi.fn(), destroy: vi.fn() };
    mockRes = { on: vi.fn(), statusCode: 200 };
  });

  it('returns a Monthly UsageItem when totalQuota has data', async () => {
    const credPath = validCredPath();
    const resetTime = new Date(Date.now() + 60_000).toISOString();
    const chunks = [
      JSON.stringify({ totalQuota: { limit: '500', used: '125', resetTime } }),
    ];
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') chunks.forEach((c) => cb(c));
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((_url: any, _opts: any, cb: any) => {
      cb(mockRes);
      return mockReq;
    });

    const result = await fetchMonthlyUsageViaOAuth(
      'https://api.kimi.com/coding/v1',
      credPath,
    );
    expect(result).not.toBeNull();
    expect(result!.label).toBe('Monthly');
    expect(result!.used).toBe(125);
    expect(result!.limit).toBe(500);
    expect(result!.percent_left).toBe(75);
    expect(result!.reset_seconds).not.toBeNull();
    fs.unlinkSync(credPath);
  });

  it('returns null when totalQuota is empty', async () => {
    const credPath = validCredPath();
    const chunks = [JSON.stringify({ totalQuota: {} })];
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') chunks.forEach((c) => cb(c));
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((_url: any, _opts: any, cb: any) => {
      cb(mockRes);
      return mockReq;
    });

    const result = await fetchMonthlyUsageViaOAuth(
      'https://api.kimi.com/coding/v1',
      credPath,
    );
    expect(result).toBeNull();
    fs.unlinkSync(credPath);
  });

  it('returns null on HTTP error status', async () => {
    const credPath = validCredPath();
    mockRes.statusCode = 429;
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') cb('Too Many Requests');
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((_url: any, _opts: any, cb: any) => {
      cb(mockRes);
      return mockReq;
    });

    const result = await fetchMonthlyUsageViaOAuth(
      'https://api.kimi.com/coding/v1',
      credPath,
    );
    expect(result).toBeNull();
    fs.unlinkSync(credPath);
  });

  it('returns null when no token is available', async () => {
    const result = await fetchMonthlyUsageViaOAuth(
      'https://api.kimi.com/coding/v1',
      '/nonexistent/path/kimi-code.json',
    );
    expect(result).toBeNull();
  });

  it('returns null on network error without throwing', async () => {
    const credPath = validCredPath();
    const errorHandlers: any[] = [];
    mockReq.on = vi.fn((event: string, cb: any) => {
      if (event === 'error') errorHandlers.push(cb);
      return mockReq;
    });
    vi.mocked(https.get).mockReturnValue(mockReq);

    const promise = fetchMonthlyUsageViaOAuth(
      'https://api.kimi.com/coding/v1',
      credPath,
    );
    errorHandlers.forEach((cb) => cb(new Error('ENOTFOUND')));
    await expect(promise).resolves.toBeNull();
    fs.unlinkSync(credPath);
  });

  it('strips a trailing slash from baseUrl', async () => {
    const credPath = validCredPath();
    let capturedUrl: any;
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') cb('{"totalQuota":{}}');
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((url: any, _opts: any, cb: any) => {
      capturedUrl = url;
      cb(mockRes);
      return mockReq;
    });

    await fetchMonthlyUsageViaOAuth('https://api.kimi.com/coding/v1/', credPath);
    expect(String(capturedUrl)).toBe('https://api.kimi.com/coding/v1/usages');
    fs.unlinkSync(credPath);
  });
});

describe('toInt', () => {
  it('parses numbers and numeric strings', () => {
    expect(toInt(5)).toBe(5);
    expect(toInt('5')).toBe(5);
    expect(toInt('1.5')).toBe(1.5);
  });
  it('returns null for invalid', () => {
    expect(toInt(null)).toBeNull();
    expect(toInt(undefined)).toBeNull();
    expect(toInt('abc')).toBeNull();
    expect(toInt(NaN)).toBeNull();
    expect(toInt(Infinity)).toBeNull();
  });
});

describe('formatDuration', () => {
  it('formats days/hours/minutes', () => {
    expect(formatDuration(2 * 86400 + 3 * 3600 + 5 * 60)).toBe('2day-short 3hour-short 5minute-short');
  });
  it('returns seconds only when under a minute', () => {
    expect(formatDuration(45)).toBe('45second-short');
  });
  it('returns 0s for zero', () => {
    expect(formatDuration(0)).toBe('0second-short');
  });
});

describe('normalizeIso', () => {
  it('truncates fractional seconds to 6 digits', () => {
    expect(normalizeIso('2025-01-01T00:00:00.1234567890Z')).toBe('2025-01-01T00:00:00.123456Z');
  });
  it('passes through when no fraction', () => {
    expect(normalizeIso('2025-01-01T00:00:00Z')).toBe('2025-01-01T00:00:00Z');
  });
});

describe('formatResetTimeAbsolute', () => {
  it('returns Unknown for invalid input', () => {
    expect(formatResetTimeAbsolute('not-a-date')).toEqual({ absolute: 'not-a-date', relative: 'Unknown' });
  });

  it('marks today resets with Today label', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2025, 0, 1, 12, 0, 0));
    const d = new Date(2025, 0, 1, 14, 0, 0);
    const iso = d.toISOString();
    const result = formatResetTimeAbsolute(iso);
    expect(result.absolute).toMatch(/^Today \d{2}:\d{2}$/);
  });

  it('formats tomorrow resets with Tomorrow label', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2025, 0, 1, 12, 0, 0));
    const d = new Date(2025, 0, 2, 9, 30, 0);
    const iso = d.toISOString();
    const result = formatResetTimeAbsolute(iso);
    expect(result.absolute).toMatch(/^Tomorrow \d{2}:\d{2}$/);
  });

  it('formats future date with weekday name', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2025, 0, 1, 12, 0, 0));
    const d = new Date(2025, 0, 4, 10, 0, 0);
    const iso = d.toISOString();
    const result = formatResetTimeAbsolute(iso);
    expect(result.absolute).toMatch(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) \d{2}:\d{2}$/);
  });

  it('handles null input in catch block', () => {
    const result = formatResetTimeAbsolute(null as any);
    expect(result.absolute).toBeDefined();
    expect(result.relative).toBe('Unknown');
  });

  it('returns Reset for past reset time', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2025, 0, 1, 12, 0, 0));
    const d = new Date(2024, 11, 31, 10, 0, 0);
    const iso = d.toISOString();
    const result = formatResetTimeAbsolute(iso);
    expect(result.relative).toBe('Reset');
  });
});

describe('isLinkIssue', () => {
  it('flags network errors', () => {
    expect(isLinkIssue(new Error('Request timeout'))).toBe(true);
    expect(isLinkIssue(new Error('getaddrinfo ENOTFOUND'))).toBe(true);
    expect(isLinkIssue(new Error('socket hang up'))).toBe(true);
    expect(isLinkIssue(new Error('invalid URL'))).toBe(true);
    expect(isLinkIssue(new Error('ECONNRESET'))).toBe(true);
    expect(isLinkIssue(new Error('network unreachable'))).toBe(true);
  });
  it('handles null and undefined error input', () => {
    expect(isLinkIssue(null)).toBe(false);
    expect(isLinkIssue(undefined)).toBe(false);
  });

  it('does not flag generic errors', () => {
    expect(isLinkIssue(new Error('HTTP 500'))).toBe(false);
    expect(isLinkIssue(new Error('something else'))).toBe(false);
  });
});

describe('localizedLimitName', () => {
  it('returns "Weekly" for weekly labels', () => {
    expect(localizedLimitName('Weekly')).toBe('Weekly');
  });
  it('returns "5 Hours" for 5-hour labels', () => {
    expect(localizedLimitName('5 Hours')).toBe('5 Hours');
  });
  it('returns "Monthly" for monthly labels', () => {
    expect(localizedLimitName('Monthly')).toBe('Monthly');
  });
  it('returns original label for unknown types', () => {
    expect(localizedLimitName('Custom Label')).toBe('Custom Label');
  });
  it('detects fiveHours from 5h shorthand', () => {
    expect(localizedLimitName('5h')).toBe('5 Hours');
  });
});

describe('shortLabel', () => {
  it('returns short label for weekly', () => {
    expect(shortLabel('Weekly')).toBe('W-Short');
  });
  it('returns short label for 5-hours', () => {
    expect(shortLabel('5 Hours')).toBe('5H-Short');
  });
  it('returns short label for monthly', () => {
    expect(shortLabel('Monthly')).toBe('M-Short');
  });
  it('truncates unknown labels to 3 chars', () => {
    expect(shortLabel('Custom')).toBe('Cus');
  });
});

describe('findWindowItem', () => {
  it('finds matching item by window type', () => {
    const items = [
      {
        label: 'Weekly',
        used: 10,
        limit: 100,
        remaining: 90,
        percent_left: 90,
        reset_hint: null,
        reset_seconds: null,
        reset_at: null,
      } as any,
      {
        label: 'Monthly',
        used: 50,
        limit: 200,
        remaining: 150,
        percent_left: 75,
        reset_hint: null,
        reset_seconds: null,
        reset_at: null,
      } as any,
    ];
    expect(findWindowItem(items, 'weekly')).toBe(items[0]);
  });
  it('returns undefined when no match', () => {
    const items = [
      {
        label: 'Weekly',
        used: 10,
        limit: 100,
        remaining: 90,
        percent_left: 90,
        reset_hint: null,
        reset_seconds: null,
        reset_at: null,
      } as any,
    ];
    expect(findWindowItem(items, 'fiveHours')).toBeUndefined();
  });
});

describe('isLowRemaining', () => {
  it('returns false for undefined item', () => {
    expect(isLowRemaining(undefined, 20)).toBe(false);
  });
  it('returns true when percent_left is below threshold', () => {
    const item = {
      label: 'Weekly',
      used: 90,
      limit: 100,
      remaining: 10,
      percent_left: 10,
      reset_hint: null,
      reset_seconds: null,
      reset_at: null,
    } as any;
    expect(isLowRemaining(item, 20)).toBe(true);
  });
  it('returns false when percent_left is above threshold', () => {
    const item = {
      label: 'Weekly',
      used: 10,
      limit: 100,
      remaining: 90,
      percent_left: 90,
      reset_hint: null,
      reset_seconds: null,
      reset_at: null,
    } as any;
    expect(isLowRemaining(item, 20)).toBe(false);
  });
});

describe('secondsUntil', () => {
  it('returns seconds for future date', () => {
    const future = new Date(Date.now() + 3600000).toISOString();
    const sec = secondsUntil(future);
    expect(sec).toBeGreaterThan(3500);
    expect(sec).toBeLessThan(3700);
  });
  it('returns null for invalid date string', () => {
    expect(secondsUntil('not-a-date')).toBeNull();
  });

  it('returns null when input causes parse error in catch', () => {
    const sec = secondsUntil(null as any);
    expect(sec).toBeNull();
  });
});

describe('formatResetTime', () => {
  it('formats future reset as duration', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2025, 0, 1, 0, 0, 0));
    const future = new Date(2025, 0, 1, 2, 0, 0).toISOString();
    expect(formatResetTime(future)).toContain('2h');
    vi.useRealTimers();
  });
  it('returns Reset for past or current time', () => {
    const past = new Date(2020, 0, 1).toISOString();
    expect(formatResetTime(past)).toBe('Reset');
  });
  it('fallback for invalid date', () => {
    const result = formatResetTime('bad-date');
    expect(result).toContain('bad-date');
  });
});

describe('setUserAgentVersion', () => {
  it('updates User-Agent header in fetchUsage', async () => {
    setUserAgentVersion('2.0.0-test');

    const mockReq = { on: vi.fn(), destroy: vi.fn() };
    const mockRes = {
      on: vi.fn((event: string, cb: any) => {
        if (event === 'data') cb(JSON.stringify({ ok: true }));
        if (event === 'end') cb();
      }),
      statusCode: 200,
    };
    let capturedOpts: any;
    vi.mocked(https.get).mockImplementation((_url: any, opts: any, cb: any) => {
      capturedOpts = opts;
      cb(mockRes);
      return mockReq;
    });

    await fetchUsage('https://api.example.com', 'sk-key');
    expect(capturedOpts.headers['User-Agent']).toBe('kimi-usage-vscode/2.0.0-test');

    setUserAgentVersion('0.1.9');
  });
});

describe('fetchUsage', () => {
  let mockReq: { on: any; destroy: any };
  let mockRes: { on: any; statusCode: number };

  beforeEach(() => {
    vi.mocked(https.get).mockReset();
    mockReq = { on: vi.fn(), destroy: vi.fn() };
    mockRes = { on: vi.fn(), statusCode: 200 };
  });

  it('fetches and parses valid JSON response', async () => {
    const chunks = [JSON.stringify({ used: 50, limit: 100 })];
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') chunks.forEach((c) => cb(c));
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((_url: any, _opts: any, cb: any) => {
      cb(mockRes);
      return mockReq;
    });

    const result = await fetchUsage('https://api.example.com', 'sk-test');
    expect(result).toEqual({ used: 50, limit: 100 });
  });

  it('includes Authorization header', async () => {
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') cb(JSON.stringify({}));
      if (event === 'end') cb();
    });
    let capturedOpts: any;
    vi.mocked(https.get).mockImplementation((_url: any, opts: any, cb: any) => {
      capturedOpts = opts;
      cb(mockRes);
      return mockReq;
    });

    await fetchUsage('https://api.example.com', 'sk-secret-key');
    expect(capturedOpts.headers['Authorization']).toBe('Bearer sk-secret-key');
  });

  it('rejects on HTTP error status', async () => {
    mockRes.statusCode = 429;
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') cb('Too Many Requests');
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((_url: any, _opts: any, cb: any) => {
      cb(mockRes);
      return mockReq;
    });

    await expect(fetchUsage('https://api.example.com', 'sk-test')).rejects.toThrow('HTTP 429');
  });

  it('rejects on invalid JSON in response', async () => {
    mockRes.on = vi.fn((event: string, cb: any) => {
      if (event === 'data') cb('not valid json');
      if (event === 'end') cb();
    });
    vi.mocked(https.get).mockImplementation((_url: any, _opts: any, cb: any) => {
      cb(mockRes);
      return mockReq;
    });

    await expect(fetchUsage('https://api.example.com', 'sk-test')).rejects.toThrow('Invalid JSON');
  });

  it('rejects on network error via req error event', async () => {
    const errorHandlers: any[] = [];
    mockReq.on = vi.fn((event: string, cb: any) => {
      if (event === 'error') errorHandlers.push(cb);
      return mockReq;
    });
    vi.mocked(https.get).mockReturnValue(mockReq);

    const fetchPromise = fetchUsage('https://api.example.com', 'sk-test');
    errorHandlers.forEach((cb) => cb(new Error('ENOTFOUND api.example.com')));

    await expect(fetchPromise).rejects.toThrow('ENOTFOUND');
  });

  it('rejects and destroys req on timeout', async () => {
    let timeoutHandler: any;
    mockReq.on = vi.fn((event: string, cb: any) => {
      if (event === 'timeout') timeoutHandler = cb;
      return mockReq;
    });
    vi.mocked(https.get).mockReturnValue(mockReq);

    const fetchPromise = fetchUsage('https://api.example.com', 'sk-test');
    timeoutHandler();

    await expect(fetchPromise).rejects.toThrow('Request timeout');
    expect(mockReq.destroy).toHaveBeenCalled();
  });
});
