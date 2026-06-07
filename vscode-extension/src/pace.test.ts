import { describe, it, expect, vi } from 'vitest';
import type { ThresholdConfig, UsageItem } from './types';
import { WEEKLY_WINDOW_SECONDS, FIVE_HOURS_WINDOW_SECONDS } from './types';
import { computePace, formatPaceBar, normalizeIconName, getPacePresentation } from './pace';

const thresholds: ThresholdConfig = { fast: 1.12, slow: 0.88 };

function makeItem(overrides: Partial<UsageItem> = {}): UsageItem {
  return {
    label: 'Weekly limit',
    used: 0,
    limit: 100,
    remaining: 100,
    percent_left: 100,
    reset_hint: null,
    reset_seconds: null,
    reset_at: null,
    ...overrides,
  };
}

describe('computePace', () => {
  it('returns null when reset_seconds missing', () => {
    expect(computePace(makeItem({ limit: 100, used: 10 }), WEEKLY_WINDOW_SECONDS, thresholds)).toBeNull();
  });

  it('returns null when reset_seconds <= 0', () => {
    expect(
      computePace(makeItem({ limit: 100, used: 10, reset_seconds: 0 }), WEEKLY_WINDOW_SECONDS, thresholds),
    ).toBeNull();
  });

  it('returns null when limit <= 0', () => {
    expect(
      computePace(makeItem({ limit: 0, used: 0, reset_seconds: 100 }), WEEKLY_WINDOW_SECONDS, thresholds),
    ).toBeNull();
  });

  it('returns null when elapsed < 1h', () => {
    const item = makeItem({ limit: 100, used: 1, reset_seconds: WEEKLY_WINDOW_SECONDS - 1800 });
    expect(computePace(item, WEEKLY_WINDOW_SECONDS, thresholds)).toBeNull();
  });

  it('classifies fast state when used ratio > elapsed ratio', () => {
    const item = makeItem({ limit: 100, used: 60, reset_seconds: WEEKLY_WINDOW_SECONDS - 2 * 86400 });
    const result = computePace(item, WEEKLY_WINDOW_SECONDS, thresholds);
    expect(result).not.toBeNull();
    expect(result!.state).toBe('fast');
  });

  it('classifies slow state when used ratio < elapsed ratio', () => {
    const item = makeItem({ limit: 100, used: 5, reset_seconds: WEEKLY_WINDOW_SECONDS - 3 * 86400 });
    const result = computePace(item, WEEKLY_WINDOW_SECONDS, thresholds);
    expect(result).not.toBeNull();
    expect(result!.state).toBe('slow');
  });

  it('classifies normal when used ratio matches elapsed ratio', () => {
    const item = makeItem({ limit: 100, used: 30, reset_seconds: WEEKLY_WINDOW_SECONDS - 3 * 86400 });
    const result = computePace(item, WEEKLY_WINDOW_SECONDS, { fast: 5.0, slow: 0.0 });
    expect(result).not.toBeNull();
    expect(result!.state).toBe('normal');
  });

  it('caps ratio at 5.0', () => {
    const item = makeItem({ limit: 100, used: 100, reset_seconds: WEEKLY_WINDOW_SECONDS - 3600 });
    const result = computePace(item, WEEKLY_WINDOW_SECONDS, thresholds);
    expect(result!.ratio).toBeLessThanOrEqual(5.0);
  });
});

describe('formatPaceBar', () => {
  it('returns 3-filled for fast state', () => {
    expect(formatPaceBar(2.0, thresholds)).toBe('\u25B0\u25B0\u25B0');
  });
  it('returns 2-filled for normal state', () => {
    expect(formatPaceBar(1.0, thresholds)).toBe('\u25B0\u25B0\u25B1');
  });
  it('returns 1-filled for slow state', () => {
    expect(formatPaceBar(0.5, thresholds)).toBe('\u25B0\u25B1\u25B1');
  });
});

describe('normalizeIconName', () => {
  it('returns fallback for empty input', () => {
    expect(normalizeIconName('', 'default')).toBe('default');
    expect(normalizeIconName('   ', 'default')).toBe('default');
  });
  it('strips $(name) wrapping', () => {
    expect(normalizeIconName('$(rocket)', 'default')).toBe('rocket');
  });
  it('rejects invalid names', () => {
    expect(normalizeIconName('Not Valid', 'default')).toBe('default');
    expect(normalizeIconName('123-start', 'default')).toBe('default');
  });
  it('accepts valid kebab-case names', () => {
    expect(normalizeIconName('arrow-up', 'default')).toBe('arrow-up');
  });
});

describe('getPacePresentation', () => {
  it('uses explicit per-state override when present', () => {
    const cfg = {
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'paceTheme') return 'Simple';
        if (key === 'paceLabels') return { fast: 'Bolt', normal: '', slow: '' };
        return def;
      }),
    } as unknown as Parameters<typeof getPacePresentation>[0];
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBe('Bolt');
  });

  it('falls back to theme label when no override', () => {
    const cfg = {
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'paceTheme') return 'Running';
        if (key === 'paceLabels') return {};
        return def;
      }),
    } as unknown as Parameters<typeof getPacePresentation>[0];
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBe('Sprint');
  });

  it('returns default icon when no override', () => {
    const cfg = {
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'paceTheme') return 'Simple';
        if (key === 'paceLabels') return {};
        if (key === 'paceIcons') return {};
        return def;
      }),
    } as unknown as Parameters<typeof getPacePresentation>[0];
    expect(getPacePresentation(cfg, 'fast').icon).toBe('warning');
    expect(getPacePresentation(cfg, 'normal').icon).toBe('dashboard');
    expect(getPacePresentation(cfg, 'slow').icon).toBe('coffee');
  });
});

describe('FIVE_HOURS_WINDOW_SECONDS', () => {
  it('equals 5 hours', () => {
    expect(FIVE_HOURS_WINDOW_SECONDS).toBe(5 * 3600);
  });
});
