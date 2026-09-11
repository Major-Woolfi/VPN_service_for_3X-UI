// i18n для веб-сайта - переводы импортируются из auto-generated файла
// Смена языка: localStorage → AuthContext (из БД) → по умолчанию ru

import { LANGUAGES } from './i18n-generated';
import type { TranslationData } from './i18n-types';

export { TranslationData };

const DEFAULT_LANG = process.env.NEXT_PUBLIC_DEFAULT_LANGUAGE || 'ru';
const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || 'vpn';
let currentLang = LANGUAGES[DEFAULT_LANG] ? DEFAULT_LANG : 'ru';

const LANG_KEY = 'vpn_language';

function getCookieValue(key: string): string | null {
  if (typeof document === 'undefined') return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${key}=`);
  if (parts.length === 2) {
    return decodeURIComponent(parts.pop()!.split(';').shift()!);
  }
  return null;
}

function initCurrentLang(): void {
  if (typeof window !== 'undefined') {
    try {
      const stored = localStorage.getItem(LANG_KEY);
      if (stored && LANGUAGES[stored]) {
        currentLang = stored;
        return;
      }
    } catch {
      // Storage can be unavailable in private/restricted browser contexts.
    }
    const cookieLang = getCookieValue(LANG_KEY);
    if (cookieLang && LANGUAGES[cookieLang]) {
      currentLang = cookieLang;
    }
  }
}

initCurrentLang();

export function getCurrentLang(): string {
  return currentLang;
}

export function setCurrentLang(lang: string): void {
  if (!LANGUAGES[lang]) return;

  const changed = currentLang !== lang;
  currentLang = lang;

  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      // Continue with the in-memory language when storage is unavailable.
    }
    const secure = window.location.protocol === 'https:' ? '; secure' : '';
    document.cookie = `${LANG_KEY}=${encodeURIComponent(lang)}; path=/; max-age=31536000; samesite=lax${secure}`;

    if (changed) {
      window.dispatchEvent(new CustomEvent('vpn-languagechange', { detail: { lang } }));
    }
  }
}

export function syncLangFromDb(lang: string): void {
  setCurrentLang(lang);
}

function resolveNested(obj: Record<string, unknown>, path: string): string | undefined {
  const parts = path.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (current === undefined || current === null) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === 'string' ? current : undefined;
}

function replacePlaceholders(text: string, params?: Record<string, string | number>): string {
  let result = text.replace(/\{vpnName\}/g, VPN_NAME);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      const escapedK = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      result = result.replace(new RegExp(`\\{${escapedK}\\}`, 'g'), String(v));
    });
  }
  return result;
}

export function t(key: string, params?: Record<string, string | number>): string {
  const lang = getCurrentLang();
  const data = LANGUAGES[lang] || LANGUAGES['ru'] || ({} as TranslationData);

  let text: string | undefined;
  if (key.startsWith('buttons.')) {
    text = resolveNested(data.buttons, key.replace('buttons.', ''));
  } else if (key.startsWith('texts.')) {
    text = resolveNested(data.texts, key.replace('texts.', ''));
  } else if (key.startsWith('legal.')) {
    text = resolveNested((data as any).legal || {}, key.replace('legal.', ''));
  }
  text = text || key;

  return replacePlaceholders(text, params);
}

export function tHtml(key: string, params?: Record<string, string | number>): string {
  const text = t(key, params);
  return text.replace(/\n/g, '<br>');
}

export function getLanguageDisplayName(code: string): string {
  const data = LANGUAGES[code];
  return data?.meta?.name || code;
}

export function getAvailableLanguages(): string[] {
  return Object.keys(LANGUAGES);
}

export async function initI18n(): Promise<void> {
  return;
}
