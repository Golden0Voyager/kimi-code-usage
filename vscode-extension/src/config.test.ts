import { describe, it, expect, vi } from 'vitest';
import {
  sanitizePercentThreshold,
  readThresholdSettings,
  readPaceThresholds,
  detectSensitivityFromThresholds,
  sanitizeHistoryRetentionDays,
  readHistoryRetentionDays,
} from './config';
import { DEFAULT_HISTORY_RETENTION_DAYS, DEFAULT_LOW_THRESHOLD } from './types';

function mockCfg(values: Record<string, unknown>) {
  return {
    get: vi.fn((key: string, def?: unknown) => (key in values ? values[key] : def)),
  } as unknown as Parameters<typeof readThresholdSettings>[0];
}

describe('sanitizePercentThreshold', () => {
  it('returns fallback for invalid values', () => {
    expect(sanitizePercentThreshold(undefined, 30)).toBe(30);
    expect(sanitizePercentThreshold(NaN, 30)).toBe(30);
  });
  it('clamps to 0-100', () => {
    expect(sanitizePercentThreshold(-5, 30)).toBe(0);
    expect(sanitizePercentThreshold(150, 30)).toBe(100);
  });
  it('passes through valid values', () => {
    expect(sanitizePercentThreshold(45, 30)).toBe(45);
  });
});

describe('readThresholdSettings', () => {
  it('returns config values when valid', () => {
    const cfg = mockCfg({ weeklyLowThresholdPercent: 25, fiveHourLowThresholdPercent: 10 });
    const result = readThresholdSettings(cfg);
    expect(result.weekly).toBe(25);
    expect(result.fiveHours).toBe(10);
  });
  it('falls back to default', () => {
    const cfg = mockCfg({});
    const result = readThresholdSettings(cfg);
    expect(result.weekly).toBe(DEFAULT_LOW_THRESHOLD);
    expect(result.fiveHours).toBe(DEFAULT_LOW_THRESHOLD);
  });
  it('clamps out-of-range values', () => {
    const cfg = mockCfg({ weeklyLowThresholdPercent: 200, fiveHourLowThresholdPercent: -1 });
    const result = readThresholdSettings(cfg);
    expect(result.weekly).toBe(100);
    expect(result.fiveHours).toBe(0);
  });
});

describe('history retention settings', () => {
  it('falls back for invalid values', () => {
    expect(sanitizeHistoryRetentionDays(undefined)).toBe(DEFAULT_HISTORY_RETENTION_DAYS);
    expect(sanitizeHistoryRetentionDays(NaN)).toBe(DEFAULT_HISTORY_RETENTION_DAYS);
  });

  it('clamps to supported package.json bounds', () => {
    expect(sanitizeHistoryRetentionDays(-5)).toBe(1);
    expect(sanitizeHistoryRetentionDays(500)).toBe(365);
  });

  it('floors fractional days', () => {
    expect(sanitizeHistoryRetentionDays(12.9)).toBe(12);
  });

  it('reads historyRetentionDays from config', () => {
    const cfg = mockCfg({ historyRetentionDays: 14 });
    expect(readHistoryRetentionDays(cfg)).toBe(14);
  });
});

describe('readPaceThresholds', () => {
  it('uses sensitivity preset when no custom values', () => {
    const cfg = mockCfg({ paceSensitivity: 'Relaxed' });
    const result = readPaceThresholds(cfg);
    expect(result).toEqual({ fast: 1.2, slow: 0.8 });
  });
  it('uses custom values when provided', () => {
    const cfg = mockCfg({ paceSensitivity: 'Normal', paceThresholdFast: 1.5, paceThresholdSlow: 0.5 });
    const result = readPaceThresholds(cfg);
    expect(result).toEqual({ fast: 1.5, slow: 0.5 });
  });
  it('falls back to Normal preset when Custom sensitivity and no overrides', () => {
    const cfg = mockCfg({ paceSensitivity: 'Custom' });
    const result = readPaceThresholds(cfg);
    expect(result).toEqual({ fast: 1.12, slow: 0.88 });
  });
});

describe('detectSensitivityFromThresholds', () => {
  it('matches a known preset', () => {
    expect(detectSensitivityFromThresholds(1.2, 0.8)).toBe('Relaxed');
    expect(detectSensitivityFromThresholds(1.05, 0.95)).toBe('Strict');
  });
  it('returns Custom for non-matching thresholds', () => {
    expect(detectSensitivityFromThresholds(1.5, 0.5)).toBe('Custom');
  });
});
