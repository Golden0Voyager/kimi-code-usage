import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---- Mock all dependencies ----
vi.mock('vscode', () => ({
  StatusBarAlignment: { Left: 1, Right: 2 },
  ThemeColor: vi.fn(function(this: any, id: string) { this.id = id; }),
  ThemeIcon: vi.fn(function(this: any, id: string) { this.id = id; }),
  MarkdownString: vi.fn(function(this: any, text: string) { this.value = text; this.isTrusted = false; }),
  window: {
    createStatusBarItem: vi.fn(() => ({
      show: vi.fn(),
      dispose: vi.fn(),
      command: '',
      text: '',
      tooltip: '',
      backgroundColor: undefined as any,
    })),
    createQuickPick: vi.fn(() => {
      const qp: any = {
        items: [] as any[],
        buttons: [] as any[],
        placeholder: '',
        matchOnDescription: false,
        matchOnDetail: false,
        show: vi.fn(),
        dispose: vi.fn(),
        hide: vi.fn(),
      };
      qp.onDidTriggerButton = vi.fn((cb: any) => { qp._btnCb = cb; return undefined as any; });
      qp.onDidAccept = vi.fn((cb: any) => { qp._acceptCb = cb; return undefined as any; });
      qp.onDidHide = vi.fn((cb: any) => { qp._hideCb = cb; return undefined as any; });
      return qp;
    }),
    showErrorMessage: vi.fn(),
    showInformationMessage: vi.fn(),
    showWarningMessage: vi.fn(),
  },
  workspace: {
    getConfiguration: vi.fn(() => ({
      get: vi.fn((key: string, def?: unknown) => {
        const defaults: Record<string, unknown> = {
          statusBarAlignment: 'Right',
          refreshIntervalMinutes: 5,
          baseUrl: 'https://api.kimi.com/coding/v1',
          showPaceIndicator: true,
          showPaceBar: true,
          redAlertCondition: 'Either',
          snapshotEnabled: false,
        };
        return key in defaults ? defaults[key] : def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    })),
  },
  Uri: { parse: vi.fn((s: string) => ({ toString: () => s })) },
  env: { openExternal: vi.fn(() => Promise.resolve(true)) },
  commands: { executeCommand: vi.fn(() => Promise.resolve()) },
  l10n: { t: (msg: string) => msg },
}));

vi.mock('./apiCache', () => ({
  fetchUsageCached: vi.fn(() =>
    Promise.resolve({ payload: { usage: { used: 50, limit: 100 } } })),
}));

vi.mock('./config', () => ({
  resolveApiKey: vi.fn(() => Promise.resolve('sk-test-key')),
  readThresholdSettings: vi.fn(() => ({ weekly: 20, fiveHours: 20 })),
  readPaceThresholds: vi.fn(() => ({ fast: 1.2, slow: 0.8 })),
}));

vi.mock('./pace', () => ({
  computePace: vi.fn(() => ({ state: 'normal', ratio: 0.9 })),
  computePace: vi.fn(() => ({ state: 'normal', ratio: 0.9 })),
  formatPaceBar: vi.fn(() => '[===]'),
  getPacePresentation: vi.fn(() => ({ icon: 'circle', label: 'Normal' })),
}));

vi.mock('./api', () => ({
  parsePayload: vi.fn(() => [
    { label: 'Weekly', used: 50, limit: 100, remaining: 50, percent_left: 50, reset_hint: null, reset_seconds: 3600, reset_at: null },
    { label: '5 Hours', used: 10, limit: 50, remaining: 40, percent_left: 80, reset_hint: null, reset_seconds: 1800, reset_at: null },
  ]),
  findWindowItem: vi.fn((items: any[], type: string) => {
    if (type === 'weekly') return items.length > 0 ? items[0] : undefined;
    if (type === 'fiveHours') return items.length > 1 ? items[1] : undefined;
    return undefined;
  }),
  isLowRemaining: vi.fn(() => false),
  localizedLimitName: vi.fn((label: string) => label),
  shortLabel: vi.fn((label: string) => label.slice(0, 3)),
  getWindowSeconds: vi.fn(() => 604800),
  formatResetTimeAbsolute: vi.fn(() => ({ absolute: 'Today 14:00', relative: '2h' })),
  detectWindowType: vi.fn(() => 'weekly'),
  isLinkIssue: vi.fn(() => false),
}));

vi.mock('./i18n', () => ({ t: (msg: string) => msg }));

// ---- Imports after mocks ----
import * as vscode from 'vscode';
import {
  setSnapshotStore,
  setNotifier,
  createStatusBarItem,
  setStatusBarCommand,
  restartInterval,
  stopInterval,
  getStatusBarItem,
  refresh,
  showDetails,
} from './statusBar';
import { resolveApiKey } from './config';
import { fetchUsageCached } from './apiCache';
import { parsePayload, isLinkIssue, isLowRemaining } from './api';

// ---- Reset module-level state between tests ----
beforeEach(() => {
  vi.clearAllMocks();
  // Clear any leaked module-level state from statusBar.ts
  stopInterval();
  setSnapshotStore(undefined as any);
  setNotifier(undefined as any);
  // Reset the internally tracked statusBarItem by disposing + recreating
  const existing = getStatusBarItem();
  if (existing) {
    existing.dispose();
  }
  // Force statusBarItem to undefined by creating a disposable that cleans up
  // Unfortunately we cannot directly set module-level variables
  // Instead, tests that need a fresh item call createStatusBarItem() themselves
});

afterEach(() => {
  stopInterval();
});

// ===================================================================
// Simple state functions
// ===================================================================

describe('setSnapshotStore / setNotifier', () => {
  it('setSnapshotStore assigns without throwing', () => {
    const mockStore = { append: vi.fn(), list: vi.fn(), clear: vi.fn(), prune: vi.fn() } as any;
    setSnapshotStore(mockStore);
  });

  it('setSnapshotStore accepts undefined', () => {
    setSnapshotStore(undefined as any);
  });

  it('setNotifier assigns without throwing', () => {
    const mockN = { checkAndNotify: vi.fn() } as any;
    setNotifier(mockN);
  });

  it('setNotifier accepts undefined', () => {
    setNotifier(undefined as any);
  });
});

// ===================================================================
// createStatusBarItem
// ===================================================================

describe('createStatusBarItem', () => {
  it('creates a new status bar item with Right alignment', () => {
    const item = createStatusBarItem();
    expect(vscode.window.createStatusBarItem).toHaveBeenCalledWith(2, 100);
    expect(item.show).toHaveBeenCalled();
  });

  it('disposes existing item before creating new one', () => {
    const first = createStatusBarItem();
    const second = createStatusBarItem();
    expect(first.dispose).toHaveBeenCalled();
  });

  it('creates status bar item with Left alignment when configured', () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'statusBarAlignment') return 'Left';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    createStatusBarItem();
    expect(vscode.window.createStatusBarItem).toHaveBeenCalledWith(1, 100);
  });
});

// ===================================================================
// setStatusBarCommand
// ===================================================================

describe('setStatusBarCommand', () => {
  it('updates command on existing item', () => {
    const item = createStatusBarItem();
    setStatusBarCommand('test.command');
    expect(item.command).toBe('test.command');
  });

  it('stores command for future items', () => {
    setStatusBarCommand('future.cmd');
    const item = createStatusBarItem();
    expect(item.command).toBe('future.cmd');
  });

  it('handles setStatusBarCommand when statusBarItem is undefined', async () => {
    vi.resetModules();
    const { setStatusBarCommand, getStatusBarItem } = await import('./statusBar');
    expect(getStatusBarItem()).toBeUndefined();
    setStatusBarCommand('test.command');
  });
});

// ===================================================================
// restartInterval / stopInterval
// ===================================================================

describe('restartInterval', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('sets an interval based on config', () => {
    const spy = vi.spyOn(global, 'setInterval');
    restartInterval();
    expect(spy).toHaveBeenCalledWith(expect.any(Function), 5 * 60 * 1000);
    spy.mockRestore();
  });

  it('clears existing interval before setting a new one', () => {
    restartInterval();
    const spy = vi.spyOn(global, 'clearInterval');
    restartInterval();
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('uses default minutes when config value is not finite', () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'refreshIntervalMinutes') return NaN;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    const spy = vi.spyOn(global, 'setInterval');
    restartInterval();
    expect(spy).toHaveBeenCalledWith(expect.any(Function), 5 * 60 * 1000);
    spy.mockRestore();
  });
});

describe('stopInterval', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('clears a running interval', () => {
    restartInterval();
    const spy = vi.spyOn(global, 'clearInterval');
    stopInterval();
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('does nothing when no interval is running', () => {
    const spy = vi.spyOn(global, 'clearInterval');
    stopInterval();
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});

// ===================================================================
// getStatusBarItem
// ===================================================================

describe('getStatusBarItem', () => {
  it('returns item after creating one', () => {
    const created = createStatusBarItem();
    expect(getStatusBarItem()).toBe(created);
  });
});

// ===================================================================
// refresh
// ===================================================================

describe('refresh', () => {
  beforeEach(async () => {
    // Ensure we have a statusBarItem for most tests
    createStatusBarItem();
  });

  it('shows API key missing when no key resolved', async () => {
    vi.mocked(resolveApiKey).mockResolvedValueOnce('');
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('API Key Missing');
  });

  it('shows error when baseUrl is empty', async () => {
    vi.mocked(resolveApiKey).mockResolvedValueOnce('sk-key');
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'baseUrl') return '';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Can you hear me');
  });

  it('shows warning when payload has no items', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([]);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Kimi: --');
  });

  it('updates status bar with usage data on success', async () => {
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('50%');
    expect(item.text.length).toBeGreaterThan(5);
  });

  it('deduplicates concurrent refresh calls', async () => {
    const p1 = refresh();
    const p2 = refresh();
    expect(p1).toBe(p2);
    await p1;
  });

  // ---- Error paths covering buildErrorPresentation branches ----
  it('handles timeout error', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('timeout'));
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Can you hear me');
  });

  it('handles HTTP 401 auth error', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('HTTP 401 Unauthorized'));
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Auth Failed');
  });

  it('handles HTTP 429 rate limit', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('HTTP 429 Rate Limited'));
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Rate Limited');
  });

  it('handles HTTP 500 server error', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('HTTP 500 Server Error'));
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Server Error');
  });

  it('handles link issue error', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('ENOTFOUND'));
    vi.mocked(isLinkIssue).mockReturnValueOnce(true);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Can you hear me');
  });

  it('handles generic request error', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('Unknown error'));
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Request Failed');
  });

  it('handles empty rejection in refresh gracefully', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(undefined);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('Request Failed');
  });

  it('calls notifier checkAndNotify when notifier is set', async () => {
    const mockNotifier = { checkAndNotify: vi.fn().mockResolvedValue(undefined) } as any;
    setNotifier(mockNotifier);
    await refresh();
    expect(mockNotifier.checkAndNotify).toHaveBeenCalled();
  });

  it('handles reset_hint in tooltip when reset_at is null', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 50, limit: 100, remaining: 50, percent_left: 50, reset_hint: 'Custom Reset Hint', reset_seconds: 3600, reset_at: null },
    ]);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.tooltip.value).toContain('Custom Reset Hint');
  });

  it('calls snapshotStore append when snapshotStore is set', async () => {
    const mockStore = { append: vi.fn().mockResolvedValue(undefined) } as any;
    setSnapshotStore(mockStore);
    await refresh();
    expect(mockStore.append).toHaveBeenCalled();
  });

  it('handles reset_at in tooltip when reset_at is provided', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 50, limit: 100, remaining: 50, percent_left: 50, reset_hint: null, reset_seconds: 3600, reset_at: '2026-06-10T22:00:00Z' },
    ]);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.tooltip.value).toContain('Refuel');
  });

  it('handles positive pace deviation sign in tooltip', async () => {
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValue({ state: 'fast', ratio: 1.5 });
    try {
      await refresh();
      const item = getStatusBarItem()!;
      expect(item.tooltip.value).toContain('+50.00%');
    } finally {
      vi.mocked(mockPace.computePace).mockReturnValue({ state: 'normal', ratio: 0.9 });
    }
  });

  it('does not show pace in tooltip when showPaceIndicator is false', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'showPaceIndicator') return false;
        if (key === 'showPaceBar') return true;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.tooltip.value).not.toContain('Normal');
  });

  it('handles redAlertCondition Weekly in status bar color', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'redAlertCondition') return 'Weekly';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.backgroundColor).toBeUndefined();
  });

  it('handles redAlertCondition 5 Hours in status bar color', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'redAlertCondition') return '5 Hours';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.backgroundColor).toBeUndefined();
  });

  it('handles null itemPace when snapshotStore is set', async () => {
    const mockStore = { append: vi.fn().mockResolvedValue(undefined) } as any;
    setSnapshotStore(mockStore);
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValue(null);
    try {
      await refresh();
      expect(mockStore.append).toHaveBeenCalled();
    } finally {
      vi.mocked(mockPace.computePace).mockReturnValue({ state: 'normal', ratio: 0.9 });
    }
  });

  // ---- Additional Coverage Tests ----
  it('shows full moon emoji when percent_left >= 99', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 0, limit: 100, remaining: 100, percent_left: 99, reset_hint: null, reset_seconds: 3600, reset_at: null }
    ]);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('\uD83C\uDF15'); // 🌕
  });

  it('shows new moon emoji when percent_left <= 1', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 99.5, limit: 100, remaining: 0.5, percent_left: 0.5, reset_hint: null, reset_seconds: 3600, reset_at: null }
    ]);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('\uD83C\uDF11'); // 🌑
  });

  it('shows fast moon emoji when paceState is fast', async () => {
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValueOnce({ state: 'fast', ratio: 1.5 });
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('\uD83C\uDF12'); // 🌔
  });

  it('shows normal moon emoji when paceState is normal', async () => {
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValueOnce({ state: 'normal', ratio: 1.0 });
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('\uD83C\uDF13'); // 🌓
  });

  it('shows slow moon emoji when paceState is slow', async () => {
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValueOnce({ state: 'slow', ratio: 0.5 });
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).toContain('\uD83C\uDF14'); // 🌗
  });

  it('handles showPaceBar: false and omits paceBarStr in prefix', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'showPaceBar') return false;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await refresh();
    const item = getStatusBarItem()!;
    expect(item.text).not.toContain('[===]');
  });

  it('handles redAlertCondition Weekly with low weekly remaining', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'redAlertCondition') return 'Weekly';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    vi.mocked(isLowRemaining).mockImplementation((item: any) => item.label === 'Weekly');
    try {
      await refresh();
      const item = getStatusBarItem()!;
      expect(item.backgroundColor).toBeDefined();
    } finally {
      vi.mocked(isLowRemaining).mockImplementation(() => false);
    }
  });

  it('handles redAlertCondition 5 Hours with low 5 Hours remaining', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'redAlertCondition') return '5 Hours';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    vi.mocked(isLowRemaining).mockImplementation((item: any) => item.label === '5 Hours');
    try {
      await refresh();
      const item = getStatusBarItem()!;
      expect(item.backgroundColor).toBeDefined();
    } finally {
      vi.mocked(isLowRemaining).mockImplementation(() => false);
    }
  });

  it('handles redAlertCondition Either with low weekly remaining', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'redAlertCondition') return 'Either';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    vi.mocked(isLowRemaining).mockImplementation((item: any) => item.label === 'Weekly');
    try {
      await refresh();
      const item = getStatusBarItem()!;
      expect(item.backgroundColor).toBeDefined();
    } finally {
      vi.mocked(isLowRemaining).mockImplementation(() => false);
    }
  });

  it('handles redAlertCondition Either with low 5 Hours remaining', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'redAlertCondition') return 'Either';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    vi.mocked(isLowRemaining).mockImplementation((item: any) => item.label === '5 Hours');
    try {
      await refresh();
      const item = getStatusBarItem()!;
      expect(item.backgroundColor).toBeDefined();
    } finally {
      vi.mocked(isLowRemaining).mockImplementation(() => false);
    }
  });
});


// ===================================================================
// showDetails
// ===================================================================

describe('showDetails', () => {
  it('shows error message when no API key', async () => {
    vi.mocked(resolveApiKey).mockResolvedValueOnce('');
    await showDetails();
    expect(vscode.window.showWarningMessage).toHaveBeenCalled();
  });

  it('shows error message when no baseUrl', async () => {
    vi.mocked(resolveApiKey).mockResolvedValueOnce('sk-key');
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'baseUrl') return '';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await showDetails();
    expect(vscode.window.showWarningMessage).toHaveBeenCalled();
  });

  it('creates QuickPick with usage items on success', async () => {
    await showDetails();
    expect(vscode.window.createQuickPick).toHaveBeenCalled();
  });

  it('handles link issue errors gracefully', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('getaddrinfo ENOTFOUND'));
    vi.mocked(isLinkIssue).mockReturnValueOnce(true);
    await showDetails();
    expect(vscode.window.showWarningMessage).toHaveBeenCalled();
  });

  it('handles HTTP 5xx errors in details view', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('HTTP 500 Internal Error'));
    await showDetails();
    expect(vscode.window.showWarningMessage).toHaveBeenCalled();
  });

  it('handles generic fetch error in details view', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(new Error('Unknown error'));
    await showDetails();
    expect(vscode.window.showWarningMessage).toHaveBeenCalled();
  });

  it('hides QuickPick on item accept', async () => {
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value as any;
    // Debug: check if onDidAccept was called at all
    expect(qp).toBeDefined();
    expect(qp.onDidAccept).toHaveBeenCalled();
    // Now get the callback
    const acceptCb = qp.onDidAccept.mock.calls[0]?.[0];
    expect(typeof acceptCb).toBe('function');
    acceptCb();
    expect(qp.hide).toHaveBeenCalled();
  });

  it('opens settings on settings button click', async () => {
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp._btnCb).toBeDefined();
    qp._btnCb({ tooltip: 'Open Settings' });
    expect(vscode.commands.executeCommand).toHaveBeenCalledWith('workbench.action.openSettings', 'kimiCodeUsage');
    expect(qp.hide).toHaveBeenCalled();
  });

  it('opens support URL on support button click', async () => {
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp._btnCb).toBeDefined();
    qp._btnCb({ tooltip: 'Buy me a coffee' });
    expect(vscode.env.openExternal).toHaveBeenCalled();
    expect(qp.hide).toHaveBeenCalled();
  });

  it('opens history on history button click', async () => {
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp._btnCb).toBeDefined();
    qp._btnCb({ tooltip: 'View Usage History' });
    expect(vscode.commands.executeCommand).toHaveBeenCalledWith('kimiCodeUsage.showHistory');
    expect(qp.hide).toHaveBeenCalled();
  });

  it('formats reset_at as detail when available', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 50, limit: 100, remaining: 50, percent_left: 50, reset_hint: null, reset_seconds: 3600, reset_at: '2025-06-15T14:00:00Z' },
    ]);
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp.items.length).toBeGreaterThan(0);
    expect(qp.items[0].detail).toContain('Resets');
  });

  it('uses reset_hint as detail when reset_at is missing', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 50, limit: 100, remaining: 50, percent_left: 50, reset_hint: 'Resets weekly', reset_seconds: null, reset_at: null },
    ]);
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp.items.length).toBeGreaterThan(0);
    expect(qp.items[0].detail).toBe('Resets weekly');
  });

  it('uses reset_at formatted details when reset_at is provided', async () => {
    vi.mocked(parsePayload).mockReturnValueOnce([
      { label: 'Weekly', used: 50, limit: 100, remaining: 50, percent_left: 50, reset_hint: null, reset_seconds: 3600, reset_at: '2026-06-10T22:00:00Z' },
    ]);
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp.items.length).toBeGreaterThan(0);
    expect(qp.items[0].detail).toContain('Resets');
  });

  it('does not show pace details in QuickPick when showPaceIndicator is false', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'showPaceIndicator') return false;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp.items.length).toBeGreaterThan(0);
    expect(qp.items[0].description).not.toContain('Pace');
  });

  it('shows positive pace deviation in QuickPick details', async () => {
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValue({ state: 'fast', ratio: 1.5 });
    try {
      await showDetails();
      const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
      expect(qp.items.length).toBeGreaterThan(0);
      expect(qp.items[0].description).toContain('+50.00%');
    } finally {
      vi.mocked(mockPace.computePace).mockReturnValue({ state: 'normal', ratio: 0.9 });
    }
  });

  it('handles unknown button click in showDetails QuickPick', async () => {
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp._btnCb).toBeDefined();
    qp._btnCb({ tooltip: 'Unknown Button' });
    // Should do nothing (no commands executed, etc.)
  });

  it('handles empty rejection in showDetails gracefully', async () => {
    vi.mocked(fetchUsageCached).mockRejectedValueOnce(undefined);
    await showDetails();
    expect(vscode.window.showWarningMessage).toHaveBeenCalled();
  });

  it('handles null pace in showDetails QuickPick details gracefully', async () => {
    const mockPace = await import('./pace');
    vi.mocked(mockPace.computePace).mockReturnValue(null);
    try {
      await showDetails();
      const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
      expect(qp.items.length).toBeGreaterThan(0);
      expect(qp.items[0].description).not.toContain('Pace');
    } finally {
      vi.mocked(mockPace.computePace).mockReturnValue({ state: 'normal', ratio: 0.9 });
    }
  });

  it('does not open support URL on support button click if supportUrl is empty', async () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key: string, def?: unknown) => {
        if (key === 'supportUrl') return '';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    } as any);
    await showDetails();
    const qp = vi.mocked(vscode.window.createQuickPick).mock.results[0]?.value;
    expect(qp._btnCb).toBeDefined();
    qp._btnCb({ tooltip: 'Buy me a coffee' });
    expect(vscode.env.openExternal).not.toHaveBeenCalled();
    expect(qp.hide).toHaveBeenCalled();
  });
});

describe('refresh without statusBarItem', () => {
  it('does nothing on refresh if statusBarItem is not created', async () => {
    vi.resetModules();
    const { refresh, getStatusBarItem } = await import('./statusBar');
    expect(getStatusBarItem()).toBeUndefined();
    await refresh();
  });
});

