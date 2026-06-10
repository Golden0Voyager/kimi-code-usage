import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('./i18n', () => ({
  currentLang: vi.fn(() => 'en'),
  t: vi.fn((s: string) => s),
}));

vi.mock('./api', () => ({
  localizedLimitName: vi.fn((label: string) => label),
}));

vi.mock('./config', () => ({
  readHistoryRetentionDays: vi.fn(() => 90),
}));

import { HistoryPanel, buildPayload, escapeHtml } from './historyPanel';
import { localizedLimitName } from './api';
import type { Snapshot, SnapshotItem } from './types';
import * as vscode from 'vscode';

function mockStore(listResult: Snapshot[] = []) {
  return { list: vi.fn().mockResolvedValue(listResult) } as any;
}

function mockContext() {
  return { asAbsolutePath: vi.fn((p: string) => `/root/${p}`) } as any;
}

function snap(
  ts: number,
  items: Array<{ wt: 'weekly' | 'fiveHours' | 'monthly'; used: number; limit: number }>,
): Snapshot {
  return {
    ts,
    items: items.map(
      (i): SnapshotItem => ({
        label: i.wt === 'weekly' ? 'Weekly limit' : i.wt === 'fiveHours' ? '5h limit' : 'Monthly limit',
        windowType: i.wt,
        used: i.used,
        limit: i.limit,
        percent_left: ((i.limit - i.used) / i.limit) * 100,
        paceRatio: null,
      }),
    ),
  };
}

describe('escapeHtml', () => {
  it('escapes ampersand', () => {
    expect(escapeHtml('a&b')).toBe('a&amp;b');
  });

  it('escapes less-than', () => {
    expect(escapeHtml('<tag>')).toBe('&lt;tag&gt;');
  });

  it('escapes double quote', () => {
    expect(escapeHtml('"hello"')).toBe('&quot;hello&quot;');
  });

  it('escapes single quote', () => {
    expect(escapeHtml("it's")).toBe('it&#39;s');
  });

  it('escapes all together', () => {
    expect(escapeHtml('<a href="x&y">')).toBe('&lt;a href=&quot;x&amp;y&quot;&gt;');
  });

  it('returns empty string for empty input', () => {
    expect(escapeHtml('')).toBe('');
  });

  it('returns safe string unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });
});

describe('HistoryPanel', () => {
  let panelsToClean: HistoryPanel[] = [];

  function track(hp: HistoryPanel) {
    panelsToClean.push(hp);
    return hp;
  }

  beforeEach(() => {
    vi.clearAllMocks();
    panelsToClean = [];
  });

  afterEach(() => {
    for (const hp of panelsToClean) {
      (hp as any).panel = undefined;
    }
  });

  it('constructor stores context and store', () => {
    const ctx = mockContext();
    const store = mockStore();
    const hp = track(new HistoryPanel(ctx, store));
    expect((hp as any).context).toBe(ctx);
    expect((hp as any).store).toBe(store);
  });

  it('mediaDir returns asAbsolutePath result', () => {
    const ctx = mockContext();
    const hp = track(new HistoryPanel(ctx, mockStore()));
    const dir = (hp as any).mediaDir();
    expect(ctx.asAbsolutePath).toHaveBeenCalledWith('out/media');
    expect(dir).toBe('/root/out/media');
  });

  it('mediaPath joins mediaDir with chart.umd.js', () => {
    const hp = track(new HistoryPanel(mockContext(), mockStore()));
    const p = (hp as any).mediaPath();
    expect(p).toContain('chart.umd.js');
  });

  it('show() creates webview panel when no existing panel', () => {
    const hp = track(new HistoryPanel(mockContext(), mockStore()));
    hp.show();

    expect(vscode.window.createWebviewPanel).toHaveBeenCalled();
    expect((hp as any).panel).toBeDefined();
  });

  it('show() reveals existing panel on second call', () => {
    const hp = track(new HistoryPanel(mockContext(), mockStore()));
    hp.show();
    const panel = (hp as any).panel;
    hp.show();

    expect(panel.reveal).toHaveBeenCalled();
  });

  it('show() sets up dispose handler that clears panel ref', () => {
    const hp = track(new HistoryPanel(mockContext(), mockStore()));
    hp.show();

    const panel = (hp as any).panel;
    const disposeHandler = panel.onDidDispose.mock.calls[0][0];
    disposeHandler();
    expect((hp as any).panel).toBeUndefined();
  });

  it('show() ignores messages without type or non-requestData type', async () => {
    const store = mockStore([snap(1, [{ wt: 'weekly', used: 10, limit: 100 }])]);
    const hp = track(new HistoryPanel(mockContext(), store));
    hp.show();

    const panel = (hp as any).panel;
    const msgHandler = panel.webview.onDidReceiveMessage.mock.calls[0][0];
    store.list.mockClear();

    await msgHandler({});
    expect(store.list).not.toHaveBeenCalled();

    await msgHandler({ type: 'other' });
    expect(store.list).not.toHaveBeenCalled();
  });

  it('show() sets up message handler for requestData', async () => {
    const store = mockStore([]);
    const hp = track(new HistoryPanel(mockContext(), store));
    hp.show();

    const panel = (hp as any).panel;
    const msgHandler = panel.webview.onDidReceiveMessage.mock.calls[0][0];
    await msgHandler({ type: 'requestData' });

    expect(store.list).toHaveBeenCalled();
  });

  it('refresh() posts data message to webview', async () => {
    const hp = track(new HistoryPanel(mockContext(), mockStore()));
    const panel = vscode.window.createWebviewPanel();
    vscode.window.createWebviewPanel.mockReturnValue(panel);
    (hp as any).panel = panel;

    const snapshots = [snap(1000, [{ wt: 'weekly', used: 10, limit: 100 }])];
    const store = mockStore(snapshots);
    (hp as any).store = store;

    await (hp as any).refresh.bind(hp)();

    expect(panel.webview.postMessage).toHaveBeenCalled();
    const call = panel.webview.postMessage.mock.calls[0][0];
    expect(call.type).toBe('data');
    expect(call.isDark).toBe(false);
    expect(call.payload.sampleSize).toBe(1);
  });

  it('refresh() does nothing when panel is disposed', async () => {
    const store = mockStore([snap(1, [{ wt: 'weekly', used: 0, limit: 100 }])]);
    const hp = track(new HistoryPanel(mockContext(), store));

    (hp as any).panel = undefined;
    await (hp as any).refresh.bind(hp)();

    expect(store.list).not.toHaveBeenCalled();
  });
});

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
          { label: 'Weekly limit', windowType: 'weekly', used: 10, limit: 100, percent_left: 90, paceRatio: null },
          { label: '5h limit', windowType: 'fiveHours', used: 5, limit: 50, percent_left: 90, paceRatio: null },
          { label: 'Custom plan', windowType: 'other', used: 1, limit: 20, percent_left: 95, paceRatio: null },
        ],
      },
      {
        ts: 2,
        items: [
          { label: 'Weekly limit', windowType: 'weekly', used: 20, limit: 100, percent_left: 80, paceRatio: null },
          { label: '5h limit', windowType: 'fiveHours', used: 8, limit: 50, percent_left: 84, paceRatio: null },
          { label: 'Custom plan', windowType: 'other', used: 3, limit: 20, percent_left: 85, paceRatio: null },
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

  it('skips items with zero or negative limit', () => {
    const snapshots: Snapshot[] = [
      {
        ts: 1,
        items: [
          { label: 'W', windowType: 'weekly', used: 10, limit: 0, percent_left: 0, paceRatio: null },
          { label: 'W', windowType: 'weekly', used: 10, limit: -1, percent_left: 0, paceRatio: null },
        ],
      },
    ];
    const payload = buildPayload(snapshots);
    expect(payload.series).toHaveLength(0);
  });

  it('uses localized name and predicts from ordered points', () => {
    const snapshots: Snapshot[] = [
      snap(3000, [{ wt: 'weekly', used: 30, limit: 100 }]),
      snap(2000, [{ wt: 'weekly', used: 20, limit: 100 }]),
      snap(1000, [{ wt: 'weekly', used: 10, limit: 100 }]),
    ];
    const payload = buildPayload(snapshots);
    expect(payload.series).toHaveLength(1);
    const s = payload.series[0];
    expect(s.points).toHaveLength(3);
    expect(s.points[0].ts).toBe(1000);
    expect(s.points[1].ts).toBe(2000);
    expect(s.points[2].ts).toBe(3000);
    expect(s.label).toBeTruthy();
  });

  it('falls back to original label when localizedLimitName returns falsy', () => {
    vi.mocked(localizedLimitName).mockReturnValue('');

    const snapshots: Snapshot[] = [snap(1, [{ wt: 'weekly', used: 10, limit: 100 }])];
    const payload = buildPayload(snapshots);
    expect(payload.series[0].label).toBe('Weekly limit');
  });
});