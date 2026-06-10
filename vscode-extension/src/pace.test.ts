import { describe, it, expect, vi } from 'vitest';
import type { ThresholdConfig, UsageItem } from './types';
import { WEEKLY_WINDOW_SECONDS, FIVE_HOURS_WINDOW_SECONDS } from './types';
import { computePace, formatPaceBar, normalizeIconName, getPacePresentation, paceConfigFor } from './pace';
import { setTranslator } from './i18n';

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
  function mockCfg(overrides: Record<string, unknown> = {}) {
    const get = vi.fn((key: string, def?: unknown) => {
      if (key === 'paceTheme') return overrides.theme ?? 'Simple';
      if (key === 'paceLabels') return overrides.labels ?? {};
      if (key === 'paceIcons') return overrides.icons ?? {};
      if (key === 'paceLabels.fast') return overrides.legacyLabel ?? '';
      if (key === 'paceIcons.fast') return overrides.legacyIcon ?? '';
      return def;
    });
    return { get } as unknown as Parameters<typeof getPacePresentation>[0];
  }

  it('uses explicit per-state override when present', () => {
    const cfg = mockCfg({ labels: { fast: 'Bolt', normal: '', slow: '' } });
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBe('Bolt');
  });

  it('falls back to theme label when no override', () => {
    const cfg = mockCfg({ theme: 'Running' });
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBe('Sprint');
  });

  it('returns default icon when no override', () => {
    const cfg = mockCfg({});
    expect(getPacePresentation(cfg, 'fast').icon).toBe('warning');
    expect(getPacePresentation(cfg, 'normal').icon).toBe('dashboard');
    expect(getPacePresentation(cfg, 'slow').icon).toBe('coffee');
  });

  it('handles missing paceLabels config (null/undefined fallback)', () => {
    const cfg = { get: vi.fn((key: string) => {
      if (key === 'paceTheme') return 'Simple';
      if (key === 'paceLabels') return null;
      return undefined;
    }) } as any;
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBeTruthy();
  });

  it('falls back to Simple theme for unknown theme', () => {
    const cfg = { get: vi.fn((key: string, def?: unknown) => {
      if (key === 'paceTheme') return 'NonExistent' as any;
      if (key === 'paceLabels') return {};
      return def;
    }) } as any;
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBeTruthy();
  });

  it('falls back to default label when all config is empty', () => {
    const cfg = { get: vi.fn((key: string, def?: unknown) => def) } as any;
    const result = getPacePresentation(cfg, 'fast');
    expect(result.label).toBe('Fast');
  });

  it('handles missing paceIcons config (null/undefined fallback)', () => {
    const cfg = { get: vi.fn((key: string) => {
      if (key === 'paceTheme') return 'Simple';
      if (key === 'paceLabels') return {};
      if (key === 'paceIcons') return null;
      return undefined;
    }) } as any;
    // When paceIcons returns null, ?? {} fallback should provide empty object
    const result = getPacePresentation(cfg, 'fast');
    expect(result.icon).toBe('warning');
  });

  it('uses icon from paceIcons object when present', () => {
    const cfg = { get: vi.fn((key: string) => {
      if (key === 'paceTheme') return 'Simple';
      if (key === 'paceLabels') return {};
      if (key === 'paceIcons') return { fast: 'custom-icon' };
      return undefined;
    }) } as any;
    // When paceIcons returns a value, ?? {} should NOT trigger
    const result = getPacePresentation(cfg, 'fast');
    expect(result.icon).toBe('custom-icon');
  });

  it('falls back to default label when translator returns empty string for theme label', () => {
    const mockT = {
      t: (msg: string) => {
        if (msg === 'Cheetah') return '';
        return msg;
      }
    } as any;
    setTranslator(mockT);
    try {
      const cfg = { get: vi.fn((key: string, def?: unknown) => {
        if (key === 'paceTheme') return 'Animals';
        return def;
      }) } as any;
      const result = getPacePresentation(cfg, 'fast');
      expect(result.label).toBe('Fast');
    } finally {
      setTranslator(undefined as any);
    }
  });
});

describe('FIVE_HOURS_WINDOW_SECONDS', () => {
  it('equals 5 hours', () => {
    expect(FIVE_HOURS_WINDOW_SECONDS).toBe(5 * 3600);
  });
});


describe('computePace edge cases', () => {
  it('handles zero elapsedRatio', () => {
    const item = {
      label: 'Weekly', used: 0, limit: 100, remaining: 100,
      percent_left: 100, reset_seconds: 604800, reset_hint: null,
      reset_at: null,
    };
    // reset_seconds === windowSeconds => elapsed = 0 => elapsedRatio = 0
    const result = computePace(item, 604800, { fast: 1.2, slow: 0.8 });
    expect(result).toBeNull();
  });
});

describe('paceConfigFor', () => {
  it('returns PACE_CONFIG for each state', () => {
    expect(paceConfigFor('fast')).toBeDefined();
    expect(paceConfigFor('slow')).toBeDefined();
    expect(paceConfigFor('normal')).toBeDefined();
    expect(paceConfigFor('fast').labelKey).toBeDefined();
  });
});
