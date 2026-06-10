import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as vscode from 'vscode';
import * as fs from 'fs';

// Mock Node.js fs module (used by Translator.loadAll for reading bundle files)
vi.mock('fs', () => {
  const bundles: Record<string, Record<string, string>> = {
    en: { hello: 'Hello', greeting: 'Hello {0}!', noproblem: 'No problem' },
    zh: { hello: '你好', greeting: '你好 {0}！' },
  };
  return {
    existsSync: vi.fn(() => true),
    readFileSync: vi.fn((path: string, encoding: string) => {
      for (const [lang, bundle] of Object.entries(bundles)) {
        if (path.includes('bundle.l10n.' + lang + '.json')) {
          return JSON.stringify(bundle);
        }
      }
      if (path.includes('bundle.l10n.zh-cn.json')) {
        return JSON.stringify(bundles['zh']);
      }
      return '{}';
    }),
    default: {} as any,
    promises: {} as any,
  };
});

// Mock vscode l10n
vi.mock('vscode', () => ({
  workspace: {
    getConfiguration: vi.fn((section?: string) => ({
      get: vi.fn((key: string, def?: any) => {
        if (key === 'language') return 'Auto';
        if (key === 'apiCacheTtlSeconds') return 300;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    })),
    onDidChangeConfiguration: vi.fn(() => ({ dispose: vi.fn() })),
  },
  env: {
    language: 'en',
  },
  l10n: { t: (message: string) => message },
}));

import {
  mapEnvLanguageToCode,
  Translator,
  setTranslator,
  t,
  currentLang,
  isZh,
  updateActiveLanguage,
} from './i18n';
import type { Translator as TranslatorType } from './i18n';

// Test i18n module

describe('mapEnvLanguageToCode', () => {
  it('maps zh-* to zh-cn', () => {
    expect(mapEnvLanguageToCode('zh-cn')).toBe('zh-cn');
    expect(mapEnvLanguageToCode('zh-tw')).toBe('zh-cn');
    expect(mapEnvLanguageToCode('zh')).toBe('zh-cn');
  });

  it('passes through non-zh languages', () => {
    expect(mapEnvLanguageToCode('en')).toBe('en');
    expect(mapEnvLanguageToCode('ja')).toBe('ja');
    expect(mapEnvLanguageToCode('fr')).toBe('fr');
  });

  it('falls back to en for unknown', () => {
    expect(mapEnvLanguageToCode('unknown')).toBe('en');
  });

  it('maps all supported language codes', () => {
    expect(mapEnvLanguageToCode('ja')).toBe('ja');
    expect(mapEnvLanguageToCode('fr')).toBe('fr');
    expect(mapEnvLanguageToCode('de')).toBe('de');
    expect(mapEnvLanguageToCode('pt')).toBe('pt');
    expect(mapEnvLanguageToCode('it')).toBe('it');
    expect(mapEnvLanguageToCode('es')).toBe('es');
    expect(mapEnvLanguageToCode('ko')).toBe('ko');
    expect(mapEnvLanguageToCode('ru')).toBe('ru');
  });
});

const mockContext = {
  extensionPath: '/ext',
} as any;

describe('Translator class', () => {
  it('constructs and loads bundles', () => {
    const tr = new Translator(mockContext);
    expect(tr).toBeDefined();
  });

  it('t() returns translated text for known keys', () => {
    const tr = new Translator(mockContext);
    expect(tr.t('hello')).toBe('Hello');
  });

  it('t() substitutes arguments', () => {
    const tr = new Translator(mockContext);
    expect(tr.t('greeting', 'World')).toBe('Hello World!');
  });

  it('t() returns key if not found in bundle', () => {
    const tr = new Translator(mockContext);
    expect(tr.t('nonexistent_key')).toBe('nonexistent_key');
  });

  it('lang() returns current language code', () => {
    const tr = new Translator(mockContext);
    expect(typeof tr.lang()).toBe('string');
  });

  it('isZh() returns boolean', () => {
    const tr = new Translator(mockContext);
    expect(typeof tr.isZh()).toBe('boolean');
  });

  it('choice() returns current language choice after update', () => {
    const tr = new Translator(mockContext);
    tr.update();
    const choice = tr.choice();
    expect(typeof choice).toBe('string');
  });

  it('update() switches language', () => {
    const tr = new Translator(mockContext);
    tr.update();
    expect(tr.lang()).toBeDefined();
  });

  it('handles missing bundle file gracefully (existsSync returns false)', () => {
    vi.mocked(fs.existsSync).mockImplementationOnce(() => false);
    const tr = new Translator(mockContext);
    // Without 'en' bundle, t() falls back to vscode.l10n.t which returns key
    expect(tr.t('hello')).toBe('hello');
    // But 'en' bundle should have been loaded after mockImplementationOnce restored
  });

  it('handles bundle load failure gracefully (catch block)', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const readFileMock = vi.mocked(fs.readFileSync);
    readFileMock.mockImplementationOnce((_path, _encoding) => 'invalid json{{{');

    const tr = new Translator(mockContext);
    expect(consoleSpy).toHaveBeenCalled();
    expect(tr).toBeDefined();
    consoleSpy.mockRestore();
  });

  it('update() uses CHOICE_TO_CODE when language is not Auto', () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key, def) => {
        if (key === 'language') return 'Chinese';
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    });

    const tr = new Translator(mockContext);
    expect(tr.lang()).toBe('zh-cn');
    expect(tr.isZh()).toBe(true);
  });

  it('t() falls back to en bundle when currentLang bundle is missing from map', () => {
    // Make existsSync return false for zh-cn bundle so it's never added to map
    const existsMock = vi.mocked(fs.existsSync);
    const origExists = existsMock.getMockImplementation();
    try {
      existsMock.mockImplementation((filePath) => {
        if (String(filePath).includes('bundle.l10n.zh-cn.json')) return false;
        return true;
      });

      vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
        get: vi.fn((key, def) => {
          if (key === 'language') return 'Chinese';
          return def;
        }),
        update: vi.fn(),
        has: vi.fn(),
        inspect: vi.fn(),
      });

      const tr = new Translator(mockContext);
      // zh-cn bundle missing from map -> ?? falls back to en bundle -> finds 'Hello'
      expect(tr.t('hello')).toBe('Hello');
    } finally {
      existsMock.mockImplementation(origExists as any);
    }
  });

  it('update() falls back to en for unknown LanguageChoice', () => {
    vi.mocked(vscode.workspace.getConfiguration).mockReturnValueOnce({
      get: vi.fn((key, def) => {
        if (key === 'language') return 'UnknownLang' as any;
        return def;
      }),
      update: vi.fn(),
      has: vi.fn(),
      inspect: vi.fn(),
    });

    const tr = new Translator(mockContext);
    expect(tr.lang()).toBe('en');
  });
});

describe('module-level helpers', () => {
  beforeEach(() => {
    setTranslator(new Translator(mockContext));
  });

  it('t() works at module level', () => {
    const result = t('hello');
    expect(result).toBe('Hello');
  });

  it('currentLang() returns a string', () => {
    expect(typeof currentLang()).toBe('string');
  });

  it('isZh() returns boolean', () => {
    expect(typeof isZh()).toBe('boolean');
  });

  it('updateActiveLanguage works', () => {
    expect(() => updateActiveLanguage()).not.toThrow();
  });

  it('setTranslator with undefined does not break module functions', () => {
    setTranslator(undefined as any);
    expect(typeof t('hello')).toBe('string');
    expect(currentLang()).toBe('en');
    expect(isZh()).toBe(false);
  });
});
