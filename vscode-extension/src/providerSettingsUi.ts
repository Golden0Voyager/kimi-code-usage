import * as vscode from 'vscode';
import { t } from './i18n';
import {
  readProviderSettings,
  writeProviderApiKey,
  writeProviderBaseUrl,
  setProviderEnabled,
} from './config';
import { listProviders } from './providers/registry';
import type { ProviderId } from './providers/types';
import { refresh } from './statusBar';

function maskKey(key: string): string {
  if (!key) return t('Not set');
  if (key.length <= 8) return `${key.slice(0, 2)}…`;
  return `${key.slice(0, 4)}…${key.slice(-4)}`;
}

interface ProviderPickItem extends vscode.QuickPickItem {
  providerId: ProviderId;
}

/**
 * Interactive provider setup: pick a provider, paste its API key in a
 * password InputBox, optionally override the base URL, then refresh.
 */
export async function configureProviders(): Promise<void> {
  const providers = listProviders();
  const cfg = vscode.workspace.getConfiguration('kimiCodeUsage');

  const picks: ProviderPickItem[] = providers.map((p) => {
    const settings = readProviderSettings(cfg, p.spec.id);
    const state = settings.apiKey
      ? settings.enabled
        ? t('Configured')
        : t('Disabled')
      : t('Not configured');
    return {
      label: p.spec.displayName,
      description: state,
      detail: `${t('API Key')}: ${maskKey(settings.apiKey)}`,
      providerId: p.spec.id,
    };
  });

  const chosen = await vscode.window.showQuickPick(picks, {
    placeHolder: t('Select a provider to configure'),
  });
  if (!chosen) return;

  const key = await vscode.window.showInputBox({
    password: true,
    prompt: t('Paste {0} API key', chosen.label),
    placeHolder: 'sk-…',
    value: readProviderSettings(cfg, chosen.providerId).apiKey,
  });
  if (key === undefined) return; // Esc cancelled; keep existing settings

  if (key) {
    await writeProviderApiKey(chosen.providerId, key);
  }

  const current = readProviderSettings(cfg, chosen.providerId).baseUrl;
  const baseUrl = await vscode.window.showInputBox({
    prompt: t('Base URL for {0} (empty = default)', chosen.label),
    value: current,
  });
  if (baseUrl === undefined) return;

  if (baseUrl && baseUrl !== current) {
    await writeProviderBaseUrl(chosen.providerId, baseUrl);
  }

  if (key || (baseUrl && baseUrl !== current)) {
    await setProviderEnabled(chosen.providerId, true);
    vscode.window.showInformationMessage(t('{0} configured.', chosen.label));
    void refresh();
  }
}
