// i18n для веб-сайта - переводы импортируются из auto-generated файла
// Смена языка: localStorage/cookie → AuthContext (из БД) → настройка по умолчанию

import { LANGUAGES } from "./i18n-generated";
import type { TranslationData } from "./i18n-types";

export { TranslationData };

function getDefaultLanguage(): string {
  const configured = process.env.NEXT_PUBLIC_DEFAULT_LANGUAGE;
  if (configured && LANGUAGES[configured]) return configured;

  const firstLanguage = Object.keys(LANGUAGES)[0];
  if (!firstLanguage) throw new Error("No languages configured");
  return firstLanguage;
}

const FALLBACK_LANG = getDefaultLanguage();
const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || "vpn";
let currentLang = FALLBACK_LANG;

const LANG_KEY = "vpn_language";

function getCookieValue(key: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${key}=`);
  if (parts.length === 2) {
    return decodeURIComponent(parts.pop()!.split(";").shift()!);
  }
  return null;
}

function initCurrentLang(): void {
  if (typeof window !== "undefined") {
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

export function setCurrentLang(lang: string): boolean {
  if (!LANGUAGES[lang]) return false;

  const changed = currentLang !== lang;
  currentLang = lang;

  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      // Continue with the in-memory language when storage is unavailable.
    }
    const secure = window.location.protocol === "https:" ? "; secure" : "";
    document.cookie = `${LANG_KEY}=${encodeURIComponent(lang)}; path=/; max-age=31536000; samesite=lax${secure}`;

    if (changed) {
      window.dispatchEvent(
        new CustomEvent("vpn-languagechange", { detail: { lang } }),
      );
    }
  }

  return true;
}

export function syncLangFromDb(lang: string): boolean {
  return setCurrentLang(lang);
}

function resolveNested(
  obj: Record<string, unknown>,
  path: string,
): string | undefined {
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current === undefined || current === null) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : undefined;
}

function replacePlaceholders(
  text: string,
  params?: Record<string, string | number>,
): string {
  let result = text.replace(/\{vpnName\}/g, VPN_NAME);
  result = result.replace(/\{siteName\}/g, VPN_NAME);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      const escapedK = k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      result = result.replace(new RegExp(`\\{${escapedK}\\}`, "g"), String(v));
    });
  }
  return result;
}

function resolveTranslation(
  data: TranslationData | undefined,
  key: string,
): string | undefined {
  if (!data) return undefined;

  if (key.startsWith("buttons.")) {
    return resolveNested(data.buttons, key.replace("buttons.", ""));
  }
  if (key.startsWith("texts.")) {
    return resolveNested(data.texts, key.replace("texts.", ""));
  }
  if (key.startsWith("legal.")) {
    return resolveNested(data.legal || {}, key.replace("legal.", ""));
  }
  return undefined;
}

export function t(
  key: string,
  params?: Record<string, string | number>,
  langOverride?: string,
): string {
  const lang =
    langOverride && LANGUAGES[langOverride] ? langOverride : getCurrentLang();
  const text =
    resolveTranslation(LANGUAGES[lang], key) ||
    resolveTranslation(LANGUAGES[FALLBACK_LANG], key) ||
    key;

  return replacePlaceholders(text, params);
}

export function tHtml(
  key: string,
  params?: Record<string, string | number>,
  langOverride?: string,
): string {
  const text = t(key, params, langOverride);
  return text.replace(/\r?\n/g, "<br>");
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
