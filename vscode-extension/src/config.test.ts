import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  sanitizePercentThreshold,
  readThresholdSettings,
  readPaceThresholds,
  detectSensitivityFromThresholds,
  sanitizeHistoryRetentionDays,
  readHistoryRetentionDays,
  resolveApiKey,
  syncSensitivityToThresholds,
} from './config';
import { DEFAULT_HISTORY_RETENTION_DAYS, DEFAULT_LOW_THRESHOLD } from './types';

import * as vscode from 'vscode';

// Module-level mutable state for vscode mock (var = no TDZ issues with hoisted vi.mock)
var mockWsFolders: any[] | undefined;
var mockCfgKey = '';
var mockEnvContent = '';
var mockReadFileReject = false;

vi.mock('vscode', () => ({
  workspace: {
    getConfiguration: vi.fn(() => ({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'apiKey') return mockCfgKey;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    })),
    get workspaceFolders() {
      return mockWsFolders;
    },
    fs: {
      readFile: vi.fn(() => {
        if (mockReadFileReject) return Promise.reject(new Error('ENOENT'));
        return Promise.resolve(new TextEncoder().encode(mockEnvContent));
      }),
    },
  },
  Uri: {
    joinPath: vi.fn((base: any, ...parts: string[]) => ({
      fsPath: '/mock/' + parts.join('/'),
    })),
  },
  l10n: { t: (msg: string) => msg },
}));

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
  it('falls back to Normal preset when sensitivity is invalid', () => {
    const cfg = mockCfg({ paceSensitivity: 'Invalid' as any });
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

  it('matches Normal preset exactly', () => {
    expect(detectSensitivityFromThresholds(1.12, 0.88)).toBe('Normal');
  });
});

describe('resolveApiKey', () => {
  beforeEach(() => {
    mockWsFolders = undefined;
    mockCfgKey = '';
    mockEnvContent = '';
    mockReadFileReject = false;
    // Override real env vars that may be set on the developer's machine
    vi.stubEnv('KIMI_CODING_API_KEY', '');
    vi.stubEnv('KIMI_API_KEY', '');
  });

  it('returns configured apiKey immediately when set', async () => {
    mockCfgKey = 'sk-configured';
    const result = await resolveApiKey();
    expect(result).toBe('sk-configured');
  });

  it('returns empty string when no workspace folders and no env vars', async () => {
    const result = await resolveApiKey();
    expect(result).toBe('');
  });

  it('reads KIMI_CODING_API_KEY from .env file', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockEnvContent = 'KIMI_CODING_API_KEY=sk-env-coding';
    const result = await resolveApiKey();
    expect(result).toBe('sk-env-coding');
  });

  it('reads KIMI_API_KEY from .env file as fallback', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockEnvContent = 'KIMI_API_KEY=sk-env-fallback';
    const result = await resolveApiKey();
    expect(result).toBe('sk-env-fallback');
  });

  it('prefers KIMI_CODING_API_KEY over KIMI_API_KEY in .env', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockEnvContent = 'KIMI_API_KEY=sk-weak\nKIMI_CODING_API_KEY=sk-strong';
    const result = await resolveApiKey();
    expect(result).toBe('sk-strong');
  });

  it('keeps the first KIMI_API_KEY when multiple are present in .env', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockEnvContent = 'KIMI_API_KEY=sk-first\nKIMI_API_KEY=sk-second';
    const result = await resolveApiKey();
    expect(result).toBe('sk-first');
  });

  it('falls back to process.env.KIMI_CODING_API_KEY when .env missing', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockReadFileReject = true;
    vi.stubEnv('KIMI_CODING_API_KEY', 'sk-process-coding');
    const result = await resolveApiKey();
    expect(result).toBe('sk-process-coding');
  });

  it('falls back to process.env.KIMI_API_KEY when .env missing', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockReadFileReject = true;
    vi.stubEnv('KIMI_API_KEY', 'sk-process');
    const result = await resolveApiKey();
    expect(result).toBe('sk-process');
  });

  it('returns empty when .env missing and no process.env vars', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockReadFileReject = true;
    const result = await resolveApiKey();
    expect(result).toBe('');
  });

  it('tries multiple workspace folders', async () => {
    mockWsFolders = [{ uri: { fsPath: '/first' } }, { uri: { fsPath: '/second' } }];
    vi.mocked(vscode.workspace.fs.readFile)
      .mockImplementationOnce(() => Promise.resolve(new TextEncoder().encode('')))
      .mockImplementationOnce(() => Promise.resolve(new TextEncoder().encode('KIMI_API_KEY=sk-second')));
    const result = await resolveApiKey();
    expect(result).toBe('sk-second');
  });

  it('uses process.env.KIMI_CODING_API_KEY when no workspace folders', async () => {
    vi.stubEnv('KIMI_CODING_API_KEY', 'sk-proc-only');
    const result = await resolveApiKey();
    expect(result).toBe('sk-proc-only');
  });

  it('uses process.env.KIMI_API_KEY when no workspace folders', async () => {
    vi.stubEnv('KIMI_API_KEY', 'sk-proc-fallback');
    const result = await resolveApiKey();
    expect(result).toBe('sk-proc-fallback');
  });

  it('prefers configured key over .env', async () => {
    mockCfgKey = 'sk-configured';
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockEnvContent = 'KIMI_API_KEY=sk-env';
    const result = await resolveApiKey();
    expect(result).toBe('sk-configured');
  });

  it('prefers .env key over process.env', async () => {
    mockWsFolders = [{ uri: { fsPath: '/test' } }];
    mockEnvContent = 'KIMI_API_KEY=sk-env';
    vi.stubEnv('KIMI_API_KEY', 'sk-process');
    const result = await resolveApiKey();
    expect(result).toBe('sk-env');
  });
});

describe('syncSensitivityToThresholds', () => {
  it('returns early when sensitivity is Custom', async () => {
    const update = vi.fn();
    const cfg = { update, get: vi.fn(), has: vi.fn(), inspect: vi.fn() } as any;
    await syncSensitivityToThresholds(cfg, 'Custom');
    expect(update).not.toHaveBeenCalled();
  });

  it('updates config with preset thresholds', async () => {
    const update = vi.fn();
    const cfg = { update, get: vi.fn(), has: vi.fn(), inspect: vi.fn() } as any;
    await syncSensitivityToThresholds(cfg, 'Relaxed');
    expect(update).toHaveBeenCalledWith('paceThresholdFast', 1.2, true);
    expect(update).toHaveBeenCalledWith('paceThresholdSlow', 0.8, true);
  });

  it('falls back to Normal preset for unknown sensitivity', async () => {
    const update = vi.fn();
    const cfg = { update, get: vi.fn(), has: vi.fn(), inspect: vi.fn() } as any;
    await syncSensitivityToThresholds(cfg, 'Unknown' as any);
    expect(update).toHaveBeenCalledWith('paceThresholdFast', 1.12, true);
    expect(update).toHaveBeenCalledWith('paceThresholdSlow', 0.88, true);
  });

  it('readPaceThresholds falls back to Normal for unknown sensitivity', () => {
    const cfg = {
      get: vi.fn((k: string) => {
        if (k === 'paceSensitivity') return 'UnknownPreset';
        return undefined;
      }),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any;
    const result = readPaceThresholds(cfg);
    expect(result.fast).toBeGreaterThan(0);
    expect(result.slow).toBeGreaterThan(0);
  });
});
