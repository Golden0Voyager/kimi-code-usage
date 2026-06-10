import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as vscode from 'vscode';

// ====== Module-level mocks ======

// Track config change listeners so we can fire them in tests
const configChangeListeners: Array<(e: any) => Promise<void> | void> = [];

// Mock workspace.onDidChangeConfiguration to actually register listeners
vi.mocked(vscode.workspace.onDidChangeConfiguration).mockImplementation(
  (listener: (e: any) => Promise<void> | void, thisArg?: any) => {
    const wrapped = thisArg ? listener.bind(thisArg) : listener;
    configChangeListeners.push(wrapped);
    return { dispose: vi.fn() };
  },
);

// A mutable config store so each test can set its own values
let cfgStore: Record<string, any> = {};

// Mock the configuration
vi.mocked(vscode.workspace.getConfiguration).mockImplementation((section?: string) => ({
  get: vi.fn((key: string, def?: any) => (key in cfgStore ? cfgStore[key] : def)),
  update: vi.fn(),
  has: vi.fn(),
  inspect: vi.fn(),
}) as any);

// Mock all extension dependency modules
vi.mock('./i18n', () => ({
  setTranslator: vi.fn(),
  updateActiveLanguage: vi.fn(),
  currentLang: vi.fn(() => 'en'),
  isZh: vi.fn(() => false),
  Translator: vi.fn().mockImplementation(function () { return { t: (s: string) => s }; }),
}));

vi.mock('./config', () => ({
  readThresholdSettings: vi.fn(() => ({ weekly: 30, fiveHours: 15 })),
  readHistoryRetentionDays: vi.fn(() => 90),
  detectSensitivityFromThresholds: vi.fn(() => 'Custom'),
  syncSensitivityToThresholds: vi.fn(),
}));

vi.mock('./statusBar', () => ({
  createStatusBarItem: vi.fn(),
  refresh: vi.fn(),
  restartInterval: vi.fn(),
  setNotifier: vi.fn(),
  setSnapshotStore: vi.fn(),
  showDetails: vi.fn(),
  stopInterval: vi.fn(),
}));

vi.mock('./storage', () => ({
  SnapshotStore: vi.fn().mockImplementation(function () { return {
    append: vi.fn(),
    list: vi.fn(),
    prune: vi.fn(),
    clear: vi.fn(),
  }; }),
  buildSnapshotPath: vi.fn((p: string) => `${p}/history.jsonl`),
}));

vi.mock('./historyPanel', () => ({
  HistoryPanel: vi.fn().mockImplementation(function () { return {
    show: vi.fn(),
  }; }),
}));

vi.mock('./notifier', () => ({
  Notifier: vi.fn().mockImplementation(function () { return {}; }),
}));

vi.mock('./apiCache', () => ({
  setCacheTtlSeconds: vi.fn(),
  clearCache: vi.fn(),
}));

vi.mock('./api', () => ({
  setUserAgentVersion: vi.fn(),
  fetchUsage: vi.fn(),
}));

// ====== Tests ======

// Helper: create a config change event with proper affectsConfiguration prefix matching
function makeConfigEvent(...changedKeys: string[]) {
  return {
    affectsConfiguration: vi.fn((target: string) => {
      // Real VS Code API does prefix matching
      return changedKeys.some(key => key === target || key.startsWith(target + '.'));
    }),
  };
}


describe('Extension activation and deactivation', () => {
  let mockContext: any;

  beforeEach(() => {
    vi.clearAllMocks();
    configChangeListeners.length = 0;
    cfgStore = {};

    mockContext = {
      subscriptions: [],
      globalStorageUri: { fsPath: '/tmp/kimi-test' },
      extension: {
        packageJSON: { version: '0.2.0-test' },
      },
      extensionMode: 1,
      globalState: { get: vi.fn(), update: vi.fn() },
      workspaceState: { get: vi.fn(), update: vi.fn() },
      storageUri: { fsPath: '/tmp/kimi-storage' },
      logUri: { fsPath: '/tmp/kimi-logs' },
    };
  });

  // ----------------------------------------------------------------
  // activate()
  // ----------------------------------------------------------------

  it('activate() sets user agent, translator, snapshot store, and notifier', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { setUserAgentVersion } = await import('./api');
    expect(setUserAgentVersion).toHaveBeenCalledWith('0.2.0-test');

    const { setTranslator } = await import('./i18n');
    expect(setTranslator).toHaveBeenCalled();

    const { SnapshotStore } = await import('./storage');
    expect(SnapshotStore).toHaveBeenCalledWith('/tmp/kimi-test/history.jsonl');

    const { setSnapshotStore } = await import('./statusBar');
    expect(setSnapshotStore).toHaveBeenCalled();

    const { Notifier } = await import('./notifier');
    expect(Notifier).toHaveBeenCalled();

    const { setNotifier } = await import('./statusBar');
    expect(setNotifier).toHaveBeenCalled();
  });

  it('activate() creates status bar and sets cache TTL', async () => {
    cfgStore = {
      apiCacheTtlSeconds: 600,
      weeklyLowThresholdPercent: 40,
      fiveHourLowThresholdPercent: 20,
      historyRetentionDays: 60,
    };

    const { activate } = await import('./extension');
    activate(mockContext);

    const { createStatusBarItem } = await import('./statusBar');
    expect(createStatusBarItem).toHaveBeenCalled();

    const { setCacheTtlSeconds } = await import('./apiCache');
    expect(setCacheTtlSeconds).toHaveBeenCalledWith(600);

    const { HistoryPanel } = await import('./historyPanel');
    expect(HistoryPanel).toHaveBeenCalled();
  });

  it('activate() registers three commands', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    expect(vscode.commands.registerCommand).toHaveBeenCalledTimes(3);
    expect(vscode.commands.registerCommand).toHaveBeenCalledWith(
      'kimiCodeUsage.refresh',
      expect.any(Function),
    );
    expect(vscode.commands.registerCommand).toHaveBeenCalledWith(
      'kimiCodeUsage.showDetails',
      expect.any(Function),
    );
    expect(vscode.commands.registerCommand).toHaveBeenCalledWith(
      'kimiCodeUsage.showHistory',
      expect.any(Function),
    );
  });

  it('activate() falls back to default VERSION when context.extension.packageJSON has no version', async () => {
    const contextWithoutVersion = {
      ...mockContext,
      extension: {
        packageJSON: {},
      },
    };
    const { activate } = await import('./extension');
    activate(contextWithoutVersion);
    const { setUserAgentVersion } = await import('./api');
    expect(setUserAgentVersion).toHaveBeenCalledWith('0.1.9');
  });

  it('activate() pushes disposables to subscriptions', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);
    // refresh, details, history, configChange, stopInterval = 5 disposables
    expect(mockContext.subscriptions.length).toBe(5);
  });

  it('activate() subscriptions can be disposed', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);
    const { stopInterval } = await import('./statusBar');
    expect(stopInterval).not.toHaveBeenCalled();
    mockContext.subscriptions.forEach((s: any) => s.dispose && s.dispose());
    expect(stopInterval).toHaveBeenCalled();
  });

  it('activate() triggers initial refresh and starts interval', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { refresh, restartInterval } = await import('./statusBar');
    expect(refresh).toHaveBeenCalled();
    expect(restartInterval).toHaveBeenCalled();
  });

  it('activate() creates config change listener', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    expect(vscode.workspace.onDidChangeConfiguration).toHaveBeenCalled();
    expect(configChangeListeners.length).toBe(1);
  });

  it('activate() reads default cache TTL when not configured', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { setCacheTtlSeconds } = await import('./apiCache');
    expect(setCacheTtlSeconds).toHaveBeenCalled();
  });

  // ----------------------------------------------------------------
  // deactivate()
  // ----------------------------------------------------------------

  it('deactivate() stops interval and clears state', async () => {
    const { activate, deactivate } = await import('./extension');
    activate(mockContext);
    vi.clearAllMocks(); // reset call counts from activation

    deactivate();

    const { stopInterval } = await import('./statusBar');
    expect(stopInterval).toHaveBeenCalled();

    const statusBar = await import('./statusBar');
    expect(statusBar.setSnapshotStore).toHaveBeenCalledWith(undefined);
    expect(statusBar.setNotifier).toHaveBeenCalledWith(undefined);

    const { clearCache } = await import('./apiCache');
    expect(clearCache).toHaveBeenCalled();
  });

  it('deactivate() can be called without activate()', async () => {
    const { deactivate } = await import('./extension');
    // Should not throw even if never activated
    expect(() => deactivate()).not.toThrow();
  });

  // ----------------------------------------------------------------
  // Commands
  // ----------------------------------------------------------------

  it('refresh command clears cache and calls refresh', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    // Find the refresh command handler and call it
    const refreshCall = vi.mocked(vscode.commands.registerCommand).mock.calls.find(
      ([name]) => name === 'kimiCodeUsage.refresh',
    );
    expect(refreshCall).toBeDefined();
    const [, handler] = refreshCall!;

    await (handler as () => Promise<void>)();

    const { clearCache } = await import('./apiCache');
    expect(clearCache).toHaveBeenCalled();

    const { refresh } = await import('./statusBar');
    expect(refresh).toHaveBeenCalled();
  });

  it('showDetails command calls showDetails', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const detailsCall = vi.mocked(vscode.commands.registerCommand).mock.calls.find(
      ([name]) => name === 'kimiCodeUsage.showDetails',
    );
    expect(detailsCall).toBeDefined();
    const [, handler] = detailsCall!;

    await (handler as () => Promise<void>)();

    const { showDetails } = await import('./statusBar');
    expect(showDetails).toHaveBeenCalled();
  });

  it('showHistory command calls historyPanel.show', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const historyCall = vi.mocked(vscode.commands.registerCommand).mock.calls.find(
      ([name]) => name === 'kimiCodeUsage.showHistory',
    );
    expect(historyCall).toBeDefined();
    const [, handler] = historyCall!;

    (handler as () => void)();

    const { HistoryPanel } = await import('./historyPanel');
    const lastPanelInstance = HistoryPanel.mock.results[0]?.value;
    expect(lastPanelInstance.show).toHaveBeenCalled();
  });

  // ----------------------------------------------------------------
  // Configuration changes
  // ----------------------------------------------------------------

  it('config change: language update calls updateActiveLanguage', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.language'));

    const { updateActiveLanguage } = await import('./i18n');
    expect(updateActiveLanguage).toHaveBeenCalled();
  });

  it('config change: status bar alignment recreates status bar', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { createStatusBarItem } = await import('./statusBar');
    vi.mocked(createStatusBarItem).mockClear();

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.statusBarAlignment'));

    expect(createStatusBarItem).toHaveBeenCalled();
  });

  it('config change: API cache TTL updates cache settings', async () => {
    cfgStore = { apiCacheTtlSeconds: 900 };

    const { activate } = await import('./extension');
    activate(mockContext);

    const { setCacheTtlSeconds } = await import('./apiCache');
    vi.mocked(setCacheTtlSeconds).mockClear();

    // Re-configure cfgStore for the config change event
    const freshCfg = {
      get: vi.fn((key: string, def?: any) => {
        if (key === 'apiCacheTtlSeconds') return 900;
        return def;
      }),
      update: vi.fn(),
    };
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue(freshCfg as any);

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.apiCacheTtlSeconds'));

    expect(setCacheTtlSeconds).toHaveBeenCalledWith(900);
  });

  it('config change: apiKey or baseUrl clears cache', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { clearCache } = await import('./apiCache');
    vi.mocked(clearCache).mockClear();

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.apiKey'));

    expect(clearCache).toHaveBeenCalled();
  });

  it('config change: threshold settings reconfigure notifier', async () => {
    cfgStore = {
      weeklyLowThresholdPercent: 50,
      fiveHourLowThresholdPercent: 25,
    };

    const { activate } = await import('./extension');
    activate(mockContext);

    const { readThresholdSettings } = await import('./config');
    const { Notifier } = await import('./notifier');
    const { setNotifier } = await import('./statusBar');
    vi.mocked(setNotifier).mockClear();

    // Make readThresholdSettings return new values
    vi.mocked(readThresholdSettings).mockReturnValue({ weekly: 50, fiveHours: 25 });

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.weeklyLowThresholdPercent'));

    expect(Notifier).toHaveBeenCalled();
    expect(setNotifier).toHaveBeenCalled();
  });

  it('config change: paceSensitivity syncs thresholds', async () => {
    cfgStore = { paceSensitivity: 'Strict' };

    const { activate } = await import('./extension');
    activate(mockContext);

    // Create a fresh config mock that returns 'Strict'
    const freshCfg = {
      get: vi.fn((key: string, def?: any) => {
        if (key === 'paceSensitivity') return 'Strict';
        return def;
      }),
      update: vi.fn(),
    };
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue(freshCfg as any);

    const { syncSensitivityToThresholds } = await import('./config');

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.paceSensitivity'));

    expect(syncSensitivityToThresholds).toHaveBeenCalledWith(freshCfg, 'Strict');
  });

  it('config change: paceSensitivity does not sync thresholds when sensitivity is Custom', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const freshCfg = {
      get: vi.fn((key: string, def?: any) => {
        if (key === 'paceSensitivity') return 'Custom';
        return def;
      }),
      update: vi.fn(),
    };
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue(freshCfg as any);

    const { syncSensitivityToThresholds } = await import('./config');
    vi.mocked(syncSensitivityToThresholds).mockClear();

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.paceSensitivity'));

    expect(syncSensitivityToThresholds).not.toHaveBeenCalled();
  });

  it('config change: both pace thresholds without sensitivity change detects sensitivity', async () => {
    const { activate } = await import('./extension');
    const { detectSensitivityFromThresholds } = await import('./config');
    vi.mocked(detectSensitivityFromThresholds).mockReturnValue('Relaxed');

    activate(mockContext);

    const freshCfg = {
      get: vi.fn((key: string, def?: any) => {
        if (key === 'paceThresholdFast') return 1.2;
        if (key === 'paceThresholdSlow') return 0.8;
        return def;
      }),
      update: vi.fn(),
    };
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue(freshCfg as any);

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.paceThresholdFast', 'kimiCodeUsage.paceThresholdSlow'));

    expect(detectSensitivityFromThresholds).toHaveBeenCalledWith(1.2, 0.8);
    expect(freshCfg.update).toHaveBeenCalledWith('paceSensitivity', 'Relaxed', true);
  });

  it('config change: does not update sensitivity when pace thresholds are not finite', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const freshCfg = {
      get: vi.fn((key: string, def?: any) => {
        if (key === 'paceThresholdFast') return undefined;
        if (key === 'paceThresholdSlow') return 0.8;
        return def;
      }),
      update: vi.fn(),
    };
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValue(freshCfg as any);

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.paceThresholdFast', 'kimiCodeUsage.paceThresholdSlow'));

    expect(freshCfg.update).not.toHaveBeenCalled();
  });

  it('config change: unrelated config does not trigger any action', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    vi.clearAllMocks();

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('editor.fontSize'));

    // No kimiCodeUsage actions should be triggered
    const { setCacheTtlSeconds, clearCache } = await import('./apiCache');
    expect(setCacheTtlSeconds).not.toHaveBeenCalled();
    expect(clearCache).not.toHaveBeenCalled();
  });

  it('config change: after any change, refresh and restartInterval are called', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { refresh, restartInterval } = await import('./statusBar');
    vi.mocked(refresh).mockClear();
    vi.mocked(restartInterval).mockClear();

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.language'));

    expect(restartInterval).toHaveBeenCalled();
    expect(refresh).toHaveBeenCalled();
  });

  it('config change: historyRetentionDays triggers pruneSnapshotStore', async () => {
    const { activate } = await import('./extension');
    activate(mockContext);

    const { SnapshotStore } = await import('./storage');
    const instance = SnapshotStore.mock.results[0].value;

    const listener = configChangeListeners[0];
    await listener(makeConfigEvent('kimiCodeUsage.historyRetentionDays'));

    expect(instance.prune).toHaveBeenCalled();
  });

  it('config change: prune error is caught and logged', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const { activate } = await import('./extension');
      activate(mockContext);

      const { SnapshotStore } = await import('./storage');
      const instance = SnapshotStore.mock.results[0].value;
      // Make prune reject to exercise the catch block in pruneSnapshotStore
      instance.prune = vi.fn().mockRejectedValue(new Error('DB locked'));

      const listener = configChangeListeners[0];
      await listener(makeConfigEvent('kimiCodeUsage.historyRetentionDays'));

      // Flush microtasks so the rejected promise from pruneSnapshotStore propagates
      await new Promise(resolve => setTimeout(resolve, 0));

      expect(consoleSpy).toHaveBeenCalledWith(
        '[KimiCodeUsage] Failed to prune history',
        expect.any(Error),
      );
    } finally {
      consoleSpy.mockRestore();
    }
  });
});
