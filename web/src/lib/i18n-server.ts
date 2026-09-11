// Серверный i18n - переводы импортируются из auto-generated файла
// Используется в Server Components

import { SERVER_LANGUAGES } from './i18n-generated';

const DEFAULT_LANG = process.env.NEXT_PUBLIC_DEFAULT_LANGUAGE || 'ru';
const FALLBACK_LANG = SERVER_LANGUAGES[DEFAULT_LANG] ? DEFAULT_LANG : 'ru';
const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || 'vpn';

interface TranslationData {
  meta: { code: string; name: string };
  buttons: Record<string, string>;
  texts: Record<string, string>;
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
  // Глобальная замена {vpnName}
  let result = text.replace(/\{vpnName\}/g, VPN_NAME);

  // Замена пользовательских плейсхолдеров
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      const escapedK = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      result = result.replace(new RegExp(`\\{${escapedK}\\}`, 'g'), String(v));
    });
  }

  return result;
}

export function tServer(
  lang: string,
  key: string,
  params?: Record<string, string | number>,
): string {
  const data = SERVER_LANGUAGES[lang] || SERVER_LANGUAGES[FALLBACK_LANG] || ({} as TranslationData);

  let text: string | undefined;
  if (key.startsWith('buttons.')) {
    text = resolveNested(data.buttons, key.replace('buttons.', ''));
  } else if (key.startsWith('texts.')) {
    text = resolveNested(data.texts, key.replace('texts.', ''));
  } else if (key.startsWith('legal.')) {
    text = resolveNested((data as any).legal || {}, key.replace('legal.', ''));
  }
  text = text || key;

  return replacePlaceholders(text!, params);
}

export function getServerLanguageName(code: string): string {
  return SERVER_LANGUAGES[code]?.meta?.name || code;
}

export function getServerLanguages(): string[] {
  return Object.keys(SERVER_LANGUAGES);
}

export function detectLanguage(acceptLanguage?: string): string {
  if (!acceptLanguage) return FALLBACK_LANG;
  const lang = acceptLanguage.split(',')[0].split('-')[0].toLowerCase();
  return SERVER_LANGUAGES[lang] ? lang : FALLBACK_LANG;
}

export function resolveLanguage(cookieLang?: string, acceptLanguage?: string): string {
  if (cookieLang && SERVER_LANGUAGES[cookieLang]) return cookieLang;
  return detectLanguage(acceptLanguage);
}
