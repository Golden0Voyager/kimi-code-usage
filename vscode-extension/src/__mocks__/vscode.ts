import { vi } from 'vitest';

export const StatusBarAlignment = {
  Left: 1,
  Right: 2,
} as const;

export class ThemeColor {
  constructor(public id: string) {}
}

export class ThemeIcon {
  constructor(
    public id: string,
    public color?: string,
  ) {}
}

export class MarkdownString {
  public isTrusted = false;
  public supportThemeIcons = false;
  constructor(public value: string) {}
}

export class Uri {
  static file(path: string): Uri {
    return new Uri(path, '');
  }
  static joinPath(base: Uri, ...paths: string[]): Uri {
    return new Uri([base.path, ...paths].join('/'), '');
  }
  constructor(
    public path: string,
    public scheme: string,
  ) {}
}

export const window = {
  createStatusBarItem: vi.fn(() => ({
    text: '',
    tooltip: undefined,
    backgroundColor: undefined,
    command: undefined,
    show: vi.fn(),
    dispose: vi.fn(),
  })),
  createQuickPick: vi.fn(() => ({
    items: [],
    placeholder: '',
    buttons: [] as unknown[],
    matchOnDescription: false,
    matchOnDetail: false,
    onDidTriggerButton: vi.fn(),
    onDidAccept: vi.fn(),
    show: vi.fn(),
    hide: vi.fn(),
    dispose: vi.fn(),
  })),
  showWarningMessage: vi.fn(),
  showInformationMessage: vi.fn(),
  showErrorMessage: vi.fn(),
};

export const workspace = {
  getConfiguration: vi.fn(() => ({
    get: vi.fn(),
    update: vi.fn(),
  })),
  onDidChangeConfiguration: vi.fn(),
  workspaceFolders: undefined as unknown,
  fs: {
    readFile: vi.fn(),
  },
};

export const env = {
  language: 'en',
  openExternal: vi.fn(),
};

export const commands = {
  registerCommand: vi.fn(() => ({ dispose: vi.fn() })),
  executeCommand: vi.fn(),
};

export const l10n = {
  t: (msg: string, ..._args: unknown[]) => msg,
};

export const ConfigurationTarget = {
  Global: 1,
  Workspace: 2,
  WorkspaceFolder: 3,
};

export class EventEmitter<T> {
  private listeners: ((e: T) => void)[] = [];
  event = (listener: (e: T) => void) => {
    this.listeners.push(listener);
    return { dispose: () => {} };
  };
  fire(data: T) {
    this.listeners.forEach((l) => l(data));
  }
  dispose() {
    this.listeners = [];
  }
}
