import { describe, it, expect } from 'vitest';
import { buildPayload } from './historyPanel';
import type { Snapshot } from './types';

function snap(
  ts: number,
  items: Array<{ wt: 'weekly' | 'fiveHours' | 'monthly'; used: number; limit: number }>,
): Snapshot {
  return {
    ts,
    items: items.map((i) => ({
      label: i.wt === 'weekly' ? 'Weekly limit' : i.wt === 'fiveHours' ? '5h limit' : 'Monthly limit',
      windowType: i.wt,
      used: i.used,
      limit: i.limit,
      percent_left: ((i.limit - i.used) / i.limit) * 100,
      paceRatio: null,
    })),
  };
}

describe('buildPayload', () => {
  it('returns empty series for empty input', () => {
    const payload = buildPayload([]);
    expect(payload.series).toEqual([]);
    expect(payload.sampleSize).toBe(0);
  });

  it('uses the supplied retention period in the payload', () => {
    const payload = buildPayload([], 14);
    expect(payload.retentionDays).toBe(14);
  });

  it('produces one series per detected window', () => {
    const snapshots: Snapshot[] = [
      snap(1, [
        { wt: 'weekly', used: 10, limit: 100 },
        { wt: 'fiveHours', used: 5, limit: 50 },
      ]),
      snap(2, [
        { wt: 'weekly', used: 20, limit: 100 },
        { wt: 'fiveHours', used: 8, limit: 50 },
      ]),
      snap(3, [
        { wt: 'weekly', used: 30, limit: 100 },
        { wt: 'fiveHours', used: 12, limit: 50 },
      ]),
    ];
    const payload = buildPayload(snapshots);
    expect(payload.series).toHaveLength(2);
    expect(payload.series.map((s) => s.windowType).sort()).toEqual(['fiveHours', 'weekly']);
  });

  it('includes prediction with sample-size confidence', () => {
    const snapshots: Snapshot[] = Array.from({ length: 5 }, (_, i) =>
      snap((i + 1) * 1000, [{ wt: 'weekly', used: 10 * (i + 1), limit: 100 }]),
    );
    const payload = buildPayload(snapshots);
    const weekly = payload.series.find((s) => s.windowType === 'weekly')!;
    expect(weekly.prediction.hasEnoughData).toBe(true);
    expect(weekly.prediction.sampleSize).toBe(5);
  });

  it('skips series with no data', () => {
    const snapshots: Snapshot[] = [snap(1, [{ wt: 'weekly', used: 10, limit: 100 }])];
    const payload = buildPayload(snapshots);
    expect(payload.series).toHaveLength(1);
    expect(payload.series[0].windowType).toBe('weekly');
  });

  it('includes series for any window type found, including "other"', () => {
    const snapshots: Snapshot[] = [
      {
        ts: 1,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 10,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
          {
            label: '5h limit',
            windowType: 'fiveHours',
            used: 5,
            limit: 50,
            percent_left: 90,
            paceRatio: null,
          },
          {
            label: 'Custom plan',
            windowType: 'other',
            used: 1,
            limit: 20,
            percent_left: 95,
            paceRatio: null,
          },
        ],
      },
      {
        ts: 2,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: 20,
            limit: 100,
            percent_left: 80,
            paceRatio: null,
          },
          {
            label: '5h limit',
            windowType: 'fiveHours',
            used: 8,
            limit: 50,
            percent_left: 84,
            paceRatio: null,
          },
          {
            label: 'Custom plan',
            windowType: 'other',
            used: 3,
            limit: 20,
            percent_left: 85,
            paceRatio: null,
          },
        ],
      },
    ];
    const payload = buildPayload(snapshots);
    const types = payload.series.map((s) => s.windowType);
    expect(types).toContain('weekly');
    expect(types).toContain('fiveHours');
    expect(types).toContain('other');
    expect(payload.series).toHaveLength(3);
  });
});
