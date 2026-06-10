import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Notifier } from './notifier';

vi.mock('vscode', () => ({
  window: {
    showInformationMessage: vi.fn().mockResolvedValue(undefined),
  },
}));

import * as vscode from 'vscode';
import { setTranslator, type Translator } from './i18n';
import type { UsageItem } from './types';

const stub = {
  t: (m: string, ...args: unknown[]) => m.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? '')),
} as unknown as Translator;
beforeEach(() => setTranslator(stub));
afterEach(() => setTranslator(undefined as unknown as Translator));

const opts = {
  weeklyWarningPercent: 30,
  weeklyCriticalPercent: 10,
  fiveHoursWarningPercent: 15,
  fiveHoursCriticalPercent: 5,
};

function item(label: string, percentLeft: number): UsageItem {
  return {
    label,
    used: 100 - percentLeft,
    limit: 100,
    remaining: percentLeft,
    percent_left: percentLeft,
    reset_hint: null,
    reset_seconds: null,
    reset_at: null,
  };
}

describe('Notifier.evaluate', () => {
  it('returns ok for healthy quotas', () => {
    const n = new Notifier(opts, vi.fn());
    const result = n.evaluate([item('Weekly limit', 80), item('5h limit', 80)]);
    expect(result.weekly).toBe('ok');
    expect(result.fiveHours).toBe('ok');
  });

  it('classifies warning and critical levels', () => {
    const n = new Notifier(opts, vi.fn());
    expect(n.evaluate([item('Weekly limit', 25), item('5h limit', 10)]).weekly).toBe('warning');
    expect(n.evaluate([item('Weekly limit', 5), item('5h limit', 1)]).weekly).toBe('critical');
  });
});

describe('Notifier.checkAndNotify', () => {
  it('uses default vscode show when no show passed', async () => {
    const n = new Notifier(opts);
    vi.mocked(vscode.window.showInformationMessage).mockClear();
    await n.checkAndNotify([item('Weekly limit', 80)], false);
    await n.checkAndNotify([item('Weekly limit', 15)], false);
    expect(vscode.window.showInformationMessage).toHaveBeenCalled();
  });

  it('does not fire on first call (no transitions)', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 80)], false);
    expect(show).not.toHaveBeenCalled();
  });

  it('fires when weekly drops from ok to warning', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 80)], false);
    await n.checkAndNotify([item('Weekly limit', 25)], false);
    expect(show).toHaveBeenCalled();
    expect(show.mock.calls.some((c) => /Weekly/.test(c[0]))).toBe(true);
  });

  it('does not re-fire on the same severity', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 80)], false);
    await n.checkAndNotify([item('Weekly limit', 25)], false);
    show.mockClear();
    await n.checkAndNotify([item('Weekly limit', 22)], false);
    expect(show).not.toHaveBeenCalled();
  });

  it('fires recovery message when severity returns to ok', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 5)], false);
    await n.checkAndNotify([item('Weekly limit', 50)], false);
    expect(show).toHaveBeenCalled();
    expect(show.mock.calls.some((c) => /recovered/i.test(c[0]))).toBe(true);
  });

  it('fires pace hot message when paceFast goes false -> true', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 80)], false);
    await n.checkAndNotify([item('Weekly limit', 80)], true);
    expect(show.mock.calls.some((c) => /hot/i.test(c[0]))).toBe(true);
  });

  it('fires pace back to normal message when paceFast goes true -> false', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 80)], true);
    await n.checkAndNotify([item('Weekly limit', 80)], false);
    expect(show.mock.calls.some((c) => /normal/i.test(c[0]))).toBe(true);
  });

  it('reset clears the dedup state', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 5)], false);
    n.reset();
    show.mockClear();
    await n.checkAndNotify([item('Weekly limit', 5)], false);
    expect(show).not.toHaveBeenCalled();
  });
  it('checkAndNotify handles critical to critical transition (no duplicate notification)', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 3), item('5h limit', 3)], false);
    show.mockClear();
    await n.checkAndNotify([item('Weekly limit', 2), item('5h limit', 2)], false);
    expect(show).not.toHaveBeenCalled();
  });

  it('fires weekly critical transition', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    const warnItem = item('Weekly', 15);
    await n.checkAndNotify([warnItem], false);
    show.mockClear();
    const criticalItem = item('Weekly', 3);
    await n.checkAndNotify([criticalItem], false);
    expect(show).toHaveBeenCalled();
    const calls = show.mock.calls.flat().join('|');
    expect(calls).toContain('critical');
  });

  it('fires 5-hour critical transition', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    const okWeekly = item('Weekly', 80);
    const okFive = item('5 Hours', 80);
    await n.checkAndNotify([okWeekly, okFive], false);
    show.mockClear();
    const criticalFive = item('5 Hours', 3);
    await n.checkAndNotify([okWeekly, criticalFive], false);
    expect(show).toHaveBeenCalled();
    const calls = show.mock.calls.flat().join('|');
    expect(calls).toContain('critical');
    expect(calls).toContain('5-hour');
  });

  it('fires 5-hour warning transition from ok', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    const okWeekly = item('Weekly', 80);
    const okFive = item('5 Hours', 80);
    await n.checkAndNotify([okWeekly, okFive], false);
    show.mockClear();
    const warnFive = item('5 Hours', 15);
    await n.checkAndNotify([okWeekly, warnFive], false);
    expect(show).toHaveBeenCalled();
    const calls = show.mock.calls.flat().join('|');
    expect(calls).toContain('running low');
  });

  it('checkAndNotify fires recovery message for fiveHours', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 3), item('5h limit', 3)], false);
    show.mockClear();
    await n.checkAndNotify([item('Weekly limit', 90), item('5h limit', 90)], false);
    expect(show).toHaveBeenCalled();
  });

  it('evaluate returns ok for empty items', () => {
    const n = new Notifier(opts);
    const result = n.evaluate([]);
    expect(result.weekly).toBe('ok');
    expect(result.fiveHours).toBe('ok');
  });
});

describe('Notifier.evaluate coverage', () => {
  it('returns critical for weekly below criticalPercent', () => {
    const n = new Notifier(opts);
    const criticalItem = item('Weekly', 5);
    const result = n.evaluate([criticalItem]);
    expect(result.weekly).toBe('critical');
  });

  it('returns critical for 5-hour below criticalPercent', () => {
    const n = new Notifier(opts);
    const criticalItem = item('5 Hours', 5);
    const result = n.evaluate([criticalItem]);
    expect(result.fiveHours).toBe('critical');
  });

  it('returns warning for 5-hour below warningPercent', () => {
    const n = new Notifier(opts);
    const warnItem = item('5 Hours', 15);
    const result = n.evaluate([warnItem]);
    expect(result.fiveHours).toBe('warning');
  });
});
