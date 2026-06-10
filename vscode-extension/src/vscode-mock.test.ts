import { describe, it, expect } from 'vitest';
import {
  StatusBarAlignment,
  ThemeColor,
  ThemeIcon,
  MarkdownString,
  Uri,
  ViewColumn,
  ColorThemeKind,
  window,
  workspace,
  env,
  commands,
  l10n,
  ConfigurationTarget,
  EventEmitter,
} from './__mocks__/vscode';

describe('VS Code Mock', () => {
  it('StatusBarAlignment and constants exist', () => {
    expect(StatusBarAlignment.Left).toBe(1);
    expect(StatusBarAlignment.Right).toBe(2);
    expect(ViewColumn.One).toBe(1);
    expect(ColorThemeKind.Light).toBe(1);
    expect(ConfigurationTarget.Global).toBe(1);
  });

  it('ThemeColor, ThemeIcon, MarkdownString work', () => {
    const tc = new ThemeColor('id');
    expect(tc.id).toBe('id');

    const ti = new ThemeIcon('id', 'color');
    expect(ti.id).toBe('id');
    expect(ti.color).toBe('color');

    const ms = new MarkdownString('val');
    expect(ms.value).toBe('val');
    expect(ms.isTrusted).toBe(false);
    expect(ms.supportThemeIcons).toBe(false);
  });

  it('Uri helper works', () => {
    const u = Uri.file('/path');
    expect(u.path).toBe('/path');

    const joined = Uri.joinPath(u, 'sub', 'dir');
    expect(joined.path).toBe('/path/sub/dir');
  });

  it('window object functions work', () => {
    const sbi = window.createStatusBarItem();
    expect(sbi.show).toBeDefined();
    sbi.show();
    sbi.dispose();

    const qp = window.createQuickPick();
    expect(qp.show).toBeDefined();

    const panel = window.createWebviewPanel();
    expect(panel.reveal).toBeDefined();
    expect(panel.webview.asWebviewUri('uri')).toBe('uri');
    panel.onDidDispose(() => {});
    panel.dispose();

    window.showWarningMessage('warn');
    window.showInformationMessage('info');
    window.showErrorMessage('err');
    expect(window.activeColorTheme.kind).toBe(1);
  });

  it('workspace object functions work', () => {
    const config = workspace.getConfiguration();
    expect(config.get).toBeDefined();
    expect(config.update).toBeDefined();

    expect(workspace.workspaceFolders).toBeUndefined();
    workspace.fs.readFile();
  });

  it('env properties work', () => {
    expect(env.language).toBe('en');
    env.openExternal();
  });

  it('commands work', () => {
    const disp = commands.registerCommand();
    disp.dispose();
    commands.executeCommand();
  });

  it('l10n works', () => {
    expect(l10n.t('hello')).toBe('hello');
  });

  it('EventEmitter works', () => {
    const ee = new EventEmitter<string>();
    let received = '';
    const disposable = ee.event((data) => {
      received = data;
    });
    ee.fire('hello');
    expect(received).toBe('hello');
    disposable.dispose();
    ee.dispose();
  });
});
