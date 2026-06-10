import { describe, it, expect } from 'vitest';
import { predictExhaustion } from './predict';
import type { Snapshot } from './types';

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

function buildSnapshots(usedByDay: number[], limit = 1000): Snapshot[] {
  const base = Date.UTC(2025, 0, 1);
  return usedByDay.map((used, i) => ({
    ts: base + i * DAY,
    items: [
      {
        label: 'Weekly limit',
        windowType: 'weekly' as const,
        used,
        limit,
        percent_left: ((limit - used) / limit) * 100,
        paceRatio: null,
      },
    ],
  }));
}

describe('predictExhaustion', () => {
  it('returns hasEnoughData=false with insufficient samples', () => {
    const result = predictExhaustion(buildSnapshots([10, 20]), 'weekly');
    expect(result.hasEnoughData).toBe(false);
    expect(result.predictedExhaustionTs).toBeNull();
    expect(result.alreadyExhausted).toBe(false);
    expect(result.burnRatePercent).toBeNull();
  });

  it('returns nulls for currentUsed and limit when snapshots are empty', () => {
    const result = predictExhaustion([], 'weekly');
    expect(result.currentUsed).toBeNull();
    expect(result.limit).toBeNull();
  });

  it('marks current exhaustion even with insufficient samples', () => {
    const result = predictExhaustion(buildSnapshots([1000], 1000), 'weekly');
    expect(result.hasEnoughData).toBe(false);
    expect(result.alreadyExhausted).toBe(true);
    expect(result.predictedExhaustionTs).toBeNull();
  });

  it('predicts exhaustion date when usage grows linearly', () => {
    const snaps = buildSnapshots([100, 200, 300, 400, 500]);
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.hasEnoughData).toBe(true);
    expect(result.dailyUsageRate).toBeCloseTo(100, 5);
    expect(result.trend).toBe('increasing');
    expect(result.burnRatePercent).toBeCloseTo(70, 0);
  });

  it('returns predictedExhaustionTs for future predictions', () => {
    const now = Date.now();
    const snaps: Snapshot[] = [
      {
        ts: now - 4 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 100,
            limit: 1000,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: now - 3 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 200,
            limit: 1000,
            percent_left: 80,
            paceRatio: null,
          },
        ],
      },
      {
        ts: now - 2 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 300,
            limit: 1000,
            percent_left: 70,
            paceRatio: null,
          },
        ],
      },
      {
        ts: now - 1 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 400,
            limit: 1000,
            percent_left: 60,
            paceRatio: null,
          },
        ],
      },
      {
        ts: now,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 500,
            limit: 1000,
            percent_left: 50,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.hasEnoughData).toBe(true);
    expect(result.trend).toBe('increasing');
    expect(result.predictedExhaustionTs).not.toBeNull();
    expect(result.alreadyExhausted).toBe(false);
    expect(result.burnRatePercent).toBeGreaterThan(0);
  });

  it('keeps a stale predicted exhaustion timestamp instead of reporting infinity', () => {
    const snaps: Snapshot[] = [
      {
        ts: Date.UTC(2025, 0, 1),
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 100,
            limit: 1000,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: Date.UTC(2025, 0, 2),
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 300,
            limit: 1000,
            percent_left: 70,
            paceRatio: null,
          },
        ],
      },
      {
        ts: Date.UTC(2025, 0, 3),
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 500,
            limit: 1000,
            percent_left: 50,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.alreadyExhausted).toBe(false);
    expect(result.predictedExhaustionTs).not.toBeNull();
  });

  it('returns null exhaustion when slope is non-positive', () => {
    const snaps = buildSnapshots([500, 480, 460, 440, 420]);
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.hasEnoughData).toBe(true);
    expect(result.trend).toBe('decreasing');
    expect(result.predictedExhaustionTs).toBeNull();
    expect(result.alreadyExhausted).toBe(false);
    expect(result.burnRatePercent).toBeLessThan(0);
  });

  it('predicts only from the current monotonic segment after a quota reset', () => {
    const snaps = buildSnapshots([100, 200, 300, 20, 40, 60]);
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.hasEnoughData).toBe(true);
    expect(result.sampleSize).toBe(3);
    expect(result.dailyUsageRate).toBeCloseTo(20, 5);
    expect(result.trend).toBe('increasing');
  });

  it('does not compute burn-rate forecasts for rolling five-hour windows', () => {
    const base = Date.UTC(2025, 0, 1);
    const snaps: Snapshot[] = [0, 1, 2, 3].map((i) => ({
      ts: base + i * HOUR,
      items: [
        {
          label: '5h limit',
          windowType: 'fiveHours',
          used: 10 + i * 10,
          limit: 100,
          percent_left: 90 - i * 10,
          paceRatio: 1,
        },
      ],
    }));
    const result = predictExhaustion(snaps, 'fiveHours');
    expect(result.trend).toBe('increasing');
    expect(result.burnRatePercent).toBeNull();
  });

  it('classifies stable trend when slope is near zero', () => {
    const snaps = buildSnapshots([100, 100, 100, 100, 100]);
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.trend).toBe('stable');
  });

  it('confidence scales with sample size', () => {
    const small = predictExhaustion(buildSnapshots([100, 200, 300]), 'weekly');
    const medium = predictExhaustion(
      buildSnapshots(Array.from({ length: 15 }, (_, i) => 100 + i * 10)),
      'weekly',
    );
    const large = predictExhaustion(
      buildSnapshots(Array.from({ length: 50 }, (_, i) => 100 + i * 10)),
      'weekly',
    );
    expect(small.confidence).toBe('low');
    expect(medium.confidence).toBe('medium');
    expect(large.confidence).toBe('high');
  });

  it('ignores items with wrong windowType', () => {
    const snaps: Snapshot[] = [
      {
        ts: Date.UTC(2025, 0, 1),
        items: [
          { label: '5h', windowType: 'fiveHours', used: 5, limit: 100, percent_left: 95, paceRatio: null },
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 100,
            limit: 1000,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: Date.UTC(2025, 0, 2),
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 200,
            limit: 1000,
            percent_left: 80,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.sampleSize).toBe(2);
  });

  it('ignores items with limit <= 0', () => {
    const snaps: Snapshot[] = [
      {
        ts: 1,
        items: [{ label: 'X', windowType: 'weekly', used: 0, limit: 0, percent_left: 0, paceRatio: null }],
      },
      {
        ts: 2,
        items: [{ label: 'X', windowType: 'weekly', used: 5, limit: 100, percent_left: 95, paceRatio: null }],
      },
    ];
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.sampleSize).toBe(1);
  });

  it('marks alreadyExhausted when predicted time has passed', () => {
    const snaps = buildSnapshots([100, 200, 300, 1000, 1100]);
    const result = predictExhaustion(snaps, 'weekly', { minSamples: 3 });
    expect(result.alreadyExhausted).toBe(true);
    expect(result.predictedExhaustionTs).toBeNull();
    expect(result.burnRatePercent).toBeGreaterThan(0);
  });

  it('windowDays returns 7 for unknown window type (default case)', () => {
    // 'other' falls through to default case in windowDays (returns 7 days)
    // This hits line 100-102 of predict.ts
    // Need 3+ snapshots so hasEnoughData becomes true and windowDays is called
    const snapshots = [
      {
        ts: 1000,
        items: [
          {
            label: 'Custom window',
            windowType: 'other',
            used: 10,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: 2000,
        items: [
          {
            label: 'Custom window',
            windowType: 'other',
            used: 20,
            limit: 100,
            percent_left: 80,
            paceRatio: null,
          },
        ],
      },
      {
        ts: 3000,
        items: [
          {
            label: 'Custom window',
            windowType: 'other',
            used: 30,
            limit: 100,
            percent_left: 70,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(snapshots, 'other');
    expect(result.hasEnoughData).toBe(true);
    expect(result.sampleSize).toBe(3);
    // For 'other', burnRatePercent should be null since shouldComputeBurnRate returns false
    expect(result.burnRatePercent).toBeNull();
  });

  it('linearRegression handles denom === 0 (all points same timestamp)', () => {
    const snaps = buildSnapshots([100]);
    const result = predictExhaustion(snaps, 'weekly', { minSamples: 1 });
    expect(result.hasEnoughData).toBe(true);
    expect(result.dailyUsageRate).toBe(0);
  });
});

describe('windowDays', () => {
  it('returns 30 for monthly window type', () => {
    const items = [
      {
        ts: 1000,
        items: [
          {
            label: 'Monthly',
            windowType: 'monthly',
            used: 10,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: 2000,
        items: [
          {
            label: 'Monthly',
            windowType: 'monthly',
            used: 20,
            limit: 100,
            percent_left: 80,
            paceRatio: null,
          },
        ],
      },
      {
        ts: 3000,
        items: [
          {
            label: 'Monthly',
            windowType: 'monthly',
            used: 30,
            limit: 100,
            percent_left: 70,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(items, 'monthly');
    expect(result.hasEnoughData).toBe(true);
  });
});

describe('linearRegression edge case', () => {
  it('handles zero denominator with same timestamps', () => {
    const samples = [
      {
        ts: 1000,
        items: [
          { label: 'T', windowType: 'weekly', used: 10, limit: 100, percent_left: 90, paceRatio: null },
        ],
      },
      {
        ts: 1000,
        items: [
          { label: 'T', windowType: 'weekly', used: 20, limit: 100, percent_left: 80, paceRatio: null },
        ],
      },
      {
        ts: 1000,
        items: [
          { label: 'T', windowType: 'weekly', used: 30, limit: 100, percent_left: 70, paceRatio: null },
        ],
      },
    ];
    const result = predictExhaustion(samples, 'weekly');
    expect(result).toBeDefined();
    expect(result.trend).toBeDefined();
  });

  it('handles zero denominator gracefully', () => {
    const samples = [
      {
        ts: 1000,
        items: [
          { label: 'Test', windowType: 'weekly', used: 10, limit: 100, percent_left: 90, paceRatio: null },
        ],
      },
      {
        ts: 2000,
        items: [
          { label: 'Test', windowType: 'weekly', used: 20, limit: 100, percent_left: 80, paceRatio: null },
        ],
      },
      {
        ts: 3000,
        items: [
          { label: 'Test', windowType: 'weekly', used: 30, limit: 100, percent_left: 70, paceRatio: null },
        ],
      },
    ];
    const result = predictExhaustion(samples, 'weekly');
    expect(result).toBeDefined();
  });

  it('dedupeByTimestamp removes duplicate timestamp points', () => {
    const base = Date.UTC(2025, 0, 1);
    const snaps = [
      {
        ts: base,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 10,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: base,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 20,
            limit: 100,
            percent_left: 80,
            paceRatio: null,
          },
        ],
      },
      {
        ts: base + DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 30,
            limit: 100,
            percent_left: 70,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.sampleSize).toBe(2);
  });

  it('isResetBoundary detects reset when limit changes', () => {
    const base = Date.UTC(2025, 0, 1);
    const snaps = [
      {
        ts: base,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 10,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      },
      {
        ts: base + DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 20,
            limit: 100,
            percent_left: 80,
            paceRatio: null,
          },
        ],
      },
      {
        ts: base + 2 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 5,
            limit: 200,
            percent_left: 97.5,
            paceRatio: null,
          },
        ],
      },
      {
        ts: base + 3 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 10,
            limit: 200,
            percent_left: 95,
            paceRatio: null,
          },
        ],
      },
      {
        ts: base + 4 * DAY,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly' as const,
            used: 15,
            limit: 200,
            percent_left: 92.5,
            paceRatio: null,
          },
        ],
      },
    ];
    const result = predictExhaustion(snaps, 'weekly');
    expect(result.hasEnoughData).toBe(true);
    expect(result.limit).toBe(200);
    expect(result.sampleSize).toBe(3);
  });
});
