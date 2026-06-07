import * as vscode from 'vscode';
import { Translator, setTranslator, updateActiveLanguage } from './i18n';
import {
  detectSensitivityFromThresholds,
  syncSensitivityToThresholds,
  readThresholdSettings,
  readHistoryRetentionDays,
} from './config';
import {
  createStatusBarItem,
  refresh,
  restartInterval,
  setNotifier,
  setSnapshotStore,
  showDetails,
  stopInterval,
} from './statusBar';
import { SnapshotStore, buildSnapshotPath } from './storage';
import { HistoryPanel } from './historyPanel';
import { Notifier } from './notifier';
import { setCacheTtlSeconds, clearCache } from './apiCache';
import { setUserAgentVersion } from './api';
import { DEFAULT_API_CACHE_TTL_SECONDS, type PaceSensitivity } from './types';

const VERSION = '0.1.9';

export function activate(context: vscode.ExtensionContext): void {
  console.log(`[KimiCodeUsage] v${VERSION} activated`);

  setUserAgentVersion((context.extension.packageJSON as { version?: string }).version ?? VERSION);

  setTranslator(new Translator(context));

  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');
  const store = new SnapshotStore(buildSnapshotPath(context.globalStorageUri.fsPath));
  setSnapshotStore(store);
  void pruneSnapshotStore(store, readHistoryRetentionDays(cfg));

  configureNotifier(cfg);

  const apiCacheTtl = cfg.get<number>('apiCacheTtlSeconds', DEFAULT_API_CACHE_TTL_SECONDS);
  setCacheTtlSeconds(apiCacheTtl);

  const historyPanel = new HistoryPanel(context, store);

  createStatusBarItem();

  const refreshCmd = vscode.commands.registerCommand('kimiCodeUsage.refresh', () => {
    clearCache();
    void refresh();
  });
  const detailsCmd = vscode.commands.registerCommand('kimiCodeUsage.showDetails', () => {
    void showDetails();
  });
  const historyCmd = vscode.commands.registerCommand('kimiCodeUsage.showHistory', () => {
    historyPanel.show();
  });

  const configChangeDisposable = vscode.workspace.onDidChangeConfiguration(async (e) => {
    if (!e.affectsConfiguration('kimiCodeUsage')) return;

    const fresh = vscode.workspace.getConfiguration('kimiCodeUsage');

    if (e.affectsConfiguration('kimiCodeUsage.language')) {
      updateActiveLanguage();
    }

    if (e.affectsConfiguration('kimiCodeUsage.statusBarAlignment')) {
      createStatusBarItem();
    }

    if (e.affectsConfiguration('kimiCodeUsage.apiCacheTtlSeconds')) {
      setCacheTtlSeconds(fresh.get<number>('apiCacheTtlSeconds', DEFAULT_API_CACHE_TTL_SECONDS));
    }

    if (e.affectsConfiguration('kimiCodeUsage.apiKey') || e.affectsConfiguration('kimiCodeUsage.baseUrl')) {
      clearCache();
    }

    if (
      e.affectsConfiguration('kimiCodeUsage.weeklyLowThresholdPercent') ||
      e.affectsConfiguration('kimiCodeUsage.fiveHourLowThresholdPercent')
    ) {
      configureNotifier(fresh);
    }

    if (e.affectsConfiguration('kimiCodeUsage.historyRetentionDays')) {
      void pruneSnapshotStore(store, readHistoryRetentionDays(fresh));
    }

    if (e.affectsConfiguration('kimiCodeUsage.paceSensitivity')) {
      const sensitivity = fresh.get<PaceSensitivity>('paceSensitivity', 'Normal');
      if (sensitivity !== 'Custom') {
        await syncSensitivityToThresholds(fresh, sensitivity);
      }
    }

    const fastChanged = e.affectsConfiguration('kimiCodeUsage.paceThresholdFast');
    const slowChanged = e.affectsConfiguration('kimiCodeUsage.paceThresholdSlow');
    const sensitivityChanged = e.affectsConfiguration('kimiCodeUsage.paceSensitivity');
    if (fastChanged && slowChanged && !sensitivityChanged) {
      const fast = fresh.get<number>('paceThresholdFast');
      const slow = fresh.get<number>('paceThresholdSlow');
      if (Number.isFinite(fast) && Number.isFinite(slow)) {
        await fresh.update('paceSensitivity', detectSensitivityFromThresholds(fast!, slow!), true);
      }
    }

    restartInterval();
    void refresh();
  });

  context.subscriptions.push(refreshCmd, detailsCmd, historyCmd, configChangeDisposable, {
    dispose: () => stopInterval(),
  });

  void refresh();
  restartInterval();
}

export function deactivate(): void {
  stopInterval();
  setSnapshotStore(undefined);
  setNotifier(undefined);
  clearCache();
}

function configureNotifier(cfg: vscode.WorkspaceConfiguration): void {
  const thresholds = readThresholdSettings(cfg);
  setNotifier(
    new Notifier({
      weeklyWarningPercent: thresholds.weekly,
      weeklyCriticalPercent: Math.max(5, Math.floor(thresholds.weekly / 3)),
      fiveHoursWarningPercent: thresholds.fiveHours,
      fiveHoursCriticalPercent: Math.max(3, Math.floor(thresholds.fiveHours / 3)),
    }),
  );
}

async function pruneSnapshotStore(store: SnapshotStore, retentionDays: number): Promise<void> {
  const cutoff = Date.now() - retentionDays * 24 * 3600 * 1000;
  try {
    await store.prune(cutoff);
  } catch (e) {
    console.error('[KimiCodeUsage] Failed to prune history', e);
  }
}
