import { describe, it, expect } from 'vitest';
import { mapEnvLanguageToCode, t, setTranslator, type Translator } from './i18n';

describe('mapEnvLanguageToCode', () => {
  it('maps zh-* to zh-cn', () => {
    expect(mapEnvLanguageToCode('zh-cn')).toBe('zh-cn');
    expect(mapEnvLanguageToCode('zh-tw')).toBe('zh-cn');
    expect(mapEnvLanguageToCode('zh')).toBe('zh-cn');
  });

  it('maps other supported prefixes', () => {
    expect(mapEnvLanguageToCode('ja-jp')).toBe('ja');
    expect(mapEnvLanguageToCode('fr-fr')).toBe('fr');
    expect(mapEnvLanguageToCode('de-de')).toBe('de');
    expect(mapEnvLanguageToCode('es-es')).toBe('es');
    expect(mapEnvLanguageToCode('ko-kr')).toBe('ko');
    expect(mapEnvLanguageToCode('ru-ru')).toBe('ru');
    expect(mapEnvLanguageToCode('pt-br')).toBe('pt');
    expect(mapEnvLanguageToCode('it-it')).toBe('it');
  });

  it('falls back to en for unknown locales', () => {
    expect(mapEnvLanguageToCode('en')).toBe('en');
    expect(mapEnvLanguageToCode('ar')).toBe('en');
    expect(mapEnvLanguageToCode('xyz')).toBe('en');
    expect(mapEnvLanguageToCode('')).toBe('en');
  });
});

describe('module-level t()', () => {
  it('returns the key when no translator is set', () => {
    setTranslator(undefined as unknown as Translator);
    expect(t('Unknown Key')).toBe('Unknown Key');
  });

  it('uses injected translator when present', () => {
    const stub = {
      t: (msg: string, ...args: unknown[]) =>
        msg.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? '')),
    } as unknown as Translator;
    setTranslator(stub);
    expect(t('Hi {0} {1}', 'a', 'b')).toBe('Hi a b');
    setTranslator(undefined as unknown as Translator);
  });
});
