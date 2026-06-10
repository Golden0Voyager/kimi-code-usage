import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import type { LanguageChoice } from './types';

type LanguageCode = 'en' | 'zh-cn' | 'ja' | 'fr' | 'de' | 'es' | 'ko' | 'ru' | 'pt' | 'it';

const SUPPORTED_LANGS: LanguageCode[] = ['en', 'zh-cn', 'ja', 'fr', 'de', 'es', 'ko', 'ru', 'pt', 'it'];

const CHOICE_TO_CODE: Record<Exclude<LanguageChoice, 'Auto'>, LanguageCode> = {
  English: 'en',
  Chinese: 'zh-cn',
  Japanese: 'ja',
  French: 'fr',
  German: 'de',
  Spanish: 'es',
  Korean: 'ko',
  Russian: 'ru',
  Portuguese: 'pt',
  Italian: 'it',
};

export function mapEnvLanguageToCode(envLang: string): LanguageCode {
  if (envLang.startsWith('zh')) return 'zh-cn';
  if (envLang.startsWith('ja')) return 'ja';
  if (envLang.startsWith('fr')) return 'fr';
  if (envLang.startsWith('de')) return 'de';
  if (envLang.startsWith('es')) return 'es';
  if (envLang.startsWith('ko')) return 'ko';
  if (envLang.startsWith('ru')) return 'ru';
  if (envLang.startsWith('pt')) return 'pt';
  if (envLang.startsWith('it')) return 'it';
  return 'en';
}

export class Translator {
  private bundles = new Map<LanguageCode, Record<string, string>>();
  private currentLang: LanguageCode = 'en';
  private languageChoice: LanguageChoice = 'Auto';

  constructor(context: vscode.ExtensionContext) {
    this.loadAll(context);
    this.update();
  }

  private loadAll(context: vscode.ExtensionContext) {
    for (const lang of SUPPORTED_LANGS) {
      const filePath = path.join(context.extensionPath, 'l10n', `bundle.l10n.${lang}.json`);
      try {
        if (fs.existsSync(filePath)) {
          const content = JSON.parse(fs.readFileSync(filePath, 'utf8')) as Record<string, string>;
          this.bundles.set(lang, content);
        }
      } catch (e) {
        console.error(`[KimiCodeUsage] Failed to load l10n bundle for ${lang}`, e);
      }
    }
  }

  update() {
    const config = vscode.workspace.getConfiguration('kimiCodeUsage');
    const lang = config.get<LanguageChoice>('language', 'Auto');
    this.languageChoice = lang;

    if (lang === 'Auto') {
      this.currentLang = this.mapEnvLanguage(vscode.env.language.toLowerCase());
    } else {
      this.currentLang = CHOICE_TO_CODE[lang];
    }
  }

  private mapEnvLanguage(envLang: string): LanguageCode {
    return mapEnvLanguageToCode(envLang);
  }

  t(message: string, ...args: unknown[]): string {
    const bundle = this.bundles.get(this.currentLang) ?? this.bundles.get('en');
    let str = bundle?.[message] ?? vscode.l10n.t(message);

    if (args.length > 0) {
      for (let i = 0; i < args.length; i++) {
        str = str.split(`{${i}}`).join(String(args[i]));
      }
    }
    return str;
  }

  lang(): LanguageCode {
    return this.currentLang;
  }

  isZh(): boolean {
    return this.currentLang === 'zh-cn';
  }

  choice(): LanguageChoice {
    return this.languageChoice;
  }
}

let active: Translator | undefined;

export function setTranslator(translator: Translator): void {
  active = translator;
}

export function updateActiveLanguage(): void {
  active?.update();
}

export function t(message: string, ...args: unknown[]): string {
  if (!active) {
    return vscode.l10n.t(message, ...(args as []));
  }
  return active.t(message, ...args);
}

export function currentLang(): LanguageCode {
  return active?.lang() ?? 'en';
}

export function isZh(): boolean {
  return active?.isZh() ?? false;
}
