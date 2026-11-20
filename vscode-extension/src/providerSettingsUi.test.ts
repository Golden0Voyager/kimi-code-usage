import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as vscode from 'vscode';

vi.mock('./i18n', () => ({
  t: (msg: string, ...args: unknown[]) => msg.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? '')),
}));

vi.mock('./config', () => ({
  readProviderSettings: vi.fn(() => ({
    enabled: false,
    apiKey: '',
    baseUrl: 'https://openrouter.ai/api',
  })),
  writeProviderApiKey: vi.fn(() => Promise.resolve()),
  writeProviderBaseUrl: vi.fn(() => Promise.resolve()),
  setProviderEnabled: vi.fn(() => Promise.resolve()),
}));

vi.mock('./statusBar', () => ({
  refresh: vi.fn(() => Promise.resolve()),
}));

import { configureProviders } from './providerSettingsUi';
import {
  readProviderSettings,
  writeProviderApiKey,
  writeProviderBaseUrl,
  setProviderEnabled,
} from './config';

const OPENROUTER_PICK = { label: 'OpenRouter', providerId: 'openrouter' as const };

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.mocked(vscode.window.showQuickPick).mockReset();
  vi.mocked(vscode.window.showInputBox).mockReset();
});

describe('configureProviders', () => {
  it('shows providers with masked key state in the picker', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(undefined);
    await configureProviders();
    const picks = vi.mocked(vscode.window.showQuickPick).mock.calls[0]![0] as Array<{
      label: string;
      description: string;
      detail: string;
    }>;
    expect(picks.map((p) => p.label)).toEqual(['Kimi Code', 'OpenRouter', 'Anthropic', 'OpenAI']);
    expect(picks[1]!.description).toBe('Not configured');
    expect(picks[1]!.detail).toBe('API Key: Not set');
  });

  it('masks short and long keys differently', async () => {
    vi.mocked(readProviderSettings).mockImplementation(
      () => ({ enabled: true, apiKey: 'sk-or-v1-abcdef-xyz', baseUrl: 'x' }) as never,
    );
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(undefined);
    await configureProviders();
    const picks = vi.mocked(vscode.window.showQuickPick).mock.calls[0]![0] as Array<{
      detail: string;
    }>;
    expect(picks[0]!.detail).toBe('API Key: sk-o…-xyz');

    vi.mocked(readProviderSettings).mockImplementation(
      () => ({ enabled: true, apiKey: 'short', baseUrl: 'x' }) as never,
    );
    await configureProviders();
    const picks2 = vi.mocked(vscode.window.showQuickPick).mock.calls[1]![0] as Array<{
      detail: string;
    }>;
    expect(picks2[0]!.detail).toBe('API Key: sh…');
  });

  it('full flow: paste key, keep base URL default, enable and refresh', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox).mockResolvedValueOnce('sk-or-new-key').mockResolvedValueOnce('');

    await configureProviders();

    expect(writeProviderApiKey).toHaveBeenCalledWith('openrouter', 'sk-or-new-key');
    expect(writeProviderBaseUrl).not.toHaveBeenCalled();
    expect(setProviderEnabled).toHaveBeenCalledWith('openrouter', true);
    expect(vscode.window.showInformationMessage).toHaveBeenCalledWith('OpenRouter configured.');
  });

  it('shows Disabled when a key exists but the provider is off', async () => {
    vi.mocked(readProviderSettings).mockImplementation(
      () => ({ enabled: false, apiKey: 'sk-or', baseUrl: 'x' }) as never,
    );
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(undefined);
    await configureProviders();
    const picks = vi.mocked(vscode.window.showQuickPick).mock.calls[0]![0] as Array<{
      description: string;
    }>;
    expect(picks[1]!.description).toBe('Disabled');
  });

  it('enables and refreshes when only the base URL changed', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox)
      .mockResolvedValueOnce('')
      .mockResolvedValueOnce('https://proxy.local/api');

    await configureProviders();

    expect(writeProviderApiKey).not.toHaveBeenCalled();
    expect(writeProviderBaseUrl).toHaveBeenCalledWith('openrouter', 'https://proxy.local/api');
    expect(setProviderEnabled).toHaveBeenCalledWith('openrouter', true);
  });

  it('asks for the key with a password input box', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox).mockResolvedValueOnce('sk-key').mockResolvedValueOnce('');

    await configureProviders();

    expect(vscode.window.showInputBox).toHaveBeenCalledWith(
      expect.objectContaining({ password: true, placeHolder: 'sk-…' }),
    );
  });

  it('writes a changed base URL', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox)
      .mockResolvedValueOnce('sk-key')
      .mockResolvedValueOnce('https://proxy.local/api');

    await configureProviders();

    expect(writeProviderBaseUrl).toHaveBeenCalledWith('openrouter', 'https://proxy.local/api');
  });

  it('returns without writes when the provider pick is cancelled', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(undefined);
    await configureProviders();
    expect(writeProviderApiKey).not.toHaveBeenCalled();
    expect(vscode.window.showInputBox).not.toHaveBeenCalled();
  });

  it('returns without writes when the key input is cancelled', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox).mockResolvedValueOnce(undefined);

    await configureProviders();

    expect(writeProviderApiKey).not.toHaveBeenCalled();
    expect(setProviderEnabled).not.toHaveBeenCalled();
  });

  it('keeps the key write but skips enable when the base URL input is cancelled', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox).mockResolvedValueOnce('sk-key').mockResolvedValueOnce(undefined);

    await configureProviders();

    expect(writeProviderApiKey).toHaveBeenCalledWith('openrouter', 'sk-key');
    expect(writeProviderBaseUrl).not.toHaveBeenCalled();
    expect(setProviderEnabled).not.toHaveBeenCalled();
  });

  it('does nothing when both inputs are empty', async () => {
    vi.mocked(vscode.window.showQuickPick).mockResolvedValue(OPENROUTER_PICK as never);
    vi.mocked(vscode.window.showInputBox).mockResolvedValueOnce('').mockResolvedValueOnce('');

    await configureProviders();

    expect(writeProviderApiKey).not.toHaveBeenCalled();
    expect(writeProviderBaseUrl).not.toHaveBeenCalled();
    expect(setProviderEnabled).not.toHaveBeenCalled();
    expect(vscode.window.showInformationMessage).not.toHaveBeenCalled();
  });
});
