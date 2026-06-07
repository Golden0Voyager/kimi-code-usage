import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Notifier } from './notifier';
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

  it('reset clears the dedup state', async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const n = new Notifier(opts, show);
    await n.checkAndNotify([item('Weekly limit', 5)], false);
    n.reset();
    show.mockClear();
    await n.checkAndNotify([item('Weekly limit', 5)], false);
    expect(show).not.toHaveBeenCalled();
  });
});
