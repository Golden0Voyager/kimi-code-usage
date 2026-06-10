import type { Snapshot, WindowType } from './types';

export type Trend = 'increasing' | 'decreasing' | 'stable';
export type Confidence = 'low' | 'medium' | 'high' | 'none';

export interface Prediction {
  hasEnoughData: boolean;
  sampleSize: number;
  confidence: Confidence;
  dailyUsageRate: number | null;
  burnRatePercent: number | null;
  trend: Trend;
  predictedExhaustionTs: number | null;
  currentUsed: number | null;
  limit: number | null;
  alreadyExhausted: boolean;
}

export interface PredictOptions {
  minSamples?: number;
  stableSlopeThreshold?: number;
}

const SECONDS_PER_DAY = 86400;
const DEFAULT_MIN_SAMPLES = 3;
const DEFAULT_STABLE_SLOPE = 0.5;

export function predictExhaustion(
  snapshots: Snapshot[],
  windowType: WindowType,
  options: PredictOptions = {},
): Prediction {
  const minSamples = options.minSamples ?? DEFAULT_MIN_SAMPLES;
  const stableThreshold = options.stableSlopeThreshold ?? DEFAULT_STABLE_SLOPE;

  const points = extractPoints(snapshots, windowType);
  const last = points[points.length - 1];

  if (points.length < minSamples) {
    const alreadyExhausted = !!last && last.limit > 0 && last.used >= last.limit;
    return {
      hasEnoughData: false,
      sampleSize: points.length,
      confidence: 'none',
      dailyUsageRate: null,
      burnRatePercent: null,
      trend: 'stable',
      predictedExhaustionTs: null,
      currentUsed: last ? last.used : null,
      limit: last ? last.limit : null,
      alreadyExhausted,
    };
  }

  const { slope, intercept, x0 } = linearRegression(points);
  const dailyRate = slope * SECONDS_PER_DAY;

  let trend: Trend;
  if (Math.abs(dailyRate) < stableThreshold) trend = 'stable';
  else if (dailyRate > 0) trend = 'increasing';
  else trend = 'decreasing';

  const lastPoint = points[points.length - 1];
  let predictedTs: number | null = null;
  const alreadyExhausted = !!lastPoint && lastPoint.limit > 0 && lastPoint.used >= lastPoint.limit;
  if (lastPoint && !alreadyExhausted && slope > 0) {
    const targetX = (lastPoint.limit - intercept) / slope;
    predictedTs = x0 + targetX * 1000;
  }

  const dailyQuota = lastPoint.limit / windowDays(windowType);
  const burnRatePercent =
    dailyQuota > 0 && shouldComputeBurnRate(windowType) ? (dailyRate / dailyQuota) * 100 : null;

  return {
    hasEnoughData: true,
    sampleSize: points.length,
    confidence: confidenceFor(points.length),
    dailyUsageRate: dailyRate,
    burnRatePercent,
    trend,
    predictedExhaustionTs: predictedTs,
    currentUsed: lastPoint.used,
    limit: lastPoint.limit,
    alreadyExhausted,
  };
}

function windowDays(windowType: WindowType): number {
  switch (windowType) {
    case 'weekly':
      return 7;
    case 'fiveHours':
      return 5 / 24;
    case 'monthly':
      return 30;
    default:
      return 7;
  }
}

function shouldComputeBurnRate(windowType: WindowType): boolean {
  return windowType === 'weekly' || windowType === 'monthly';
}

function extractPoints(
  snapshots: Snapshot[],
  windowType: WindowType,
): Array<{ ts: number; used: number; limit: number }> {
  const out: Array<{ ts: number; used: number; limit: number }> = [];
  for (const s of snapshots) {
    for (const item of s.items) {
      if (item.windowType !== windowType) continue;
      if (item.limit <= 0) continue;
      out.push({ ts: s.ts, used: item.used, limit: item.limit });
    }
  }
  out.sort((a, b) => a.ts - b.ts);
  return currentWindowSegment(dedupeByTimestamp(out));
}

function dedupeByTimestamp(points: Array<{ ts: number; used: number; limit: number }>): typeof points {
  const seen = new Set<number>();
  const out: typeof points = [];
  for (const p of points) {
    if (seen.has(p.ts)) continue;
    seen.add(p.ts);
    out.push(p);
  }
  return out;
}

function currentWindowSegment(points: Array<{ ts: number; used: number; limit: number }>): typeof points {
  let start = 0;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    if (isResetBoundary(prev, cur)) {
      start = i;
    }
  }
  return points.slice(start);
}

function isResetBoundary(
  prev: { used: number; limit: number },
  cur: { used: number; limit: number },
): boolean {
  if (cur.limit !== prev.limit) return true;
  if (cur.used >= prev.used) return false;
  const drop = prev.used - cur.used;
  const significantDrop = drop >= Math.max(1, cur.limit * 0.05);
  const nearEmpty = cur.limit > 0 && cur.used <= cur.limit * 0.05;
  return significantDrop || nearEmpty;
}

function linearRegression(points: Array<{ ts: number; used: number; limit: number }>) {
  const x0 = points[0].ts;
  const xs = points.map((p) => (p.ts - x0) / 1000);
  const ys = points.map((p) => p.used);
  const n = xs.length;
  const sumX = xs.reduce((a, b) => a + b, 0);
  const sumY = ys.reduce((a, b) => a + b, 0);
  const sumXY = xs.reduce((acc, x, i) => acc + x * ys[i], 0);
  const sumX2 = xs.reduce((acc, x) => acc + x * x, 0);
  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) {
    return { slope: 0, intercept: sumY / n, x0 };
  }
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept, x0 };
}

function confidenceFor(sampleSize: number): Confidence {
  if (sampleSize < 3) return 'none';
  if (sampleSize < 10) return 'low';
  if (sampleSize < 30) return 'medium';
  return 'high';
}
