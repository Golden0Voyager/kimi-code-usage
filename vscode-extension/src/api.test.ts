import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  detectWindowType,
  getWindowSeconds,
  parsePayload,
  toInt,
  formatDuration,
  normalizeIso,
  formatResetTimeAbsolute,
  isLinkIssue,
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

  it('infers used from remaining when used missing', () => {
    const payload = { usage: { remaining: 25, limit: 100, name: 'Weekly limit' } };
    const items = parsePayload(payload);
    expect(items[0].used).toBe(75);
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

  it('derives reset_seconds from reset_at when reset_in missing', () => {
    const future = new Date(Date.now() + 60_000).toISOString();
    const payload = { usage: { used: 0, limit: 100, reset_at: future, name: 'Weekly limit' } };
    const items = parsePayload(payload);
    expect(items[0].reset_seconds).not.toBeNull();
    expect(items[0].reset_seconds!).toBeGreaterThan(50);
  });

  it('skips limits entries without usable data', () => {
    const payload = { limits: [{}, { detail: { used: 5, limit: 10 } }] };
    const items = parsePayload(payload);
    expect(items).toHaveLength(1);
    expect(items[0].used).toBe(5);
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
});

describe('isLinkIssue', () => {
  it('flags network errors', () => {
    expect(isLinkIssue(new Error('Request timeout'))).toBe(true);
    expect(isLinkIssue(new Error('getaddrinfo ENOTFOUND'))).toBe(true);
    expect(isLinkIssue(new Error('socket hang up'))).toBe(true);
    expect(isLinkIssue(new Error('invalid URL'))).toBe(true);
  });
  it('does not flag generic errors', () => {
    expect(isLinkIssue(new Error('HTTP 500'))).toBe(false);
    expect(isLinkIssue(new Error('something else'))).toBe(false);
  });
});
