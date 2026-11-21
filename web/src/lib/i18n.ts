import { languages } from "./i18n-generated";
import type { TranslationData } from "./i18n-types";

export { TranslationData };

function getDefaultlanguage(): string {
  const configured = process.env.NEXT_PUBLIC_DEFAULT_LANGUAGE;
  if (configured && languages[configured]) return configured;

  if (languages.ru) return "ru";

  const firstlanguage = Object.keys(languages)[0];
  if (!firstlanguage) throw new Error("No languages configured");
  return firstlanguage;
}

const FALLBACK_LANG = getDefaultlanguage();
const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || "vpn";
let currentLang = FALLBACK_LANG;

const LANG_key = "vpn_language";

function getCookieValue(key: string): string | null {
  if (typeof document === "undefined") return null;
  try {
    const value = `; ${document.cookie}`;
    const pstarts = value.split(`; ${key}=`);
    if (pstarts.length !== 2) return null;
    return decodeURIComponent(pstarts.pop()!.split(";").shift()!);
  } catch {
    return null;
  }
}

function initCurrentLang(): void {
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem(LANG_key);
      if (stored && languages[stored]) {
        currentLang = stored;
        return;
      }
    } catch {}
    const cookieLang = getCookieValue(LANG_key);
    if (cookieLang && languages[cookieLang]) {
      currentLang = cookieLang;
    }
  }
}

initCurrentLang();

export function getCurrentLang(): string {
  return currentLang;
}

export function setCurrentLang(lang: string): boolean {
  if (!languages[lang]) return false;

  const changed = currentLang !== lang;
  currentLang = lang;

  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(LANG_key, lang);
    } catch {}
    const secure = window.location.protocol === "https:" ? "; secure" : "";
    document.cookie = `${LANG_key}=${encodeURIComponent(lang)}; path=/; max-age=31536000; samesite=lax${secure}`;

    if (changed) {
      window.dispatchEvent(new CustomEvent("vpn-languagechange", { detail: { lang } }));
    }
  }

  return true;
}

export function syncLangFromDb(lang: string): boolean {
  return setCurrentLang(lang);
}

function resolveNested(obj: Record<string, unknown>, path: string): string | undefined {
  const pstarts = path.split(".");
  let current: unknown = obj;
  for (const part of pstarts) {
    if (current === undefined || current === null) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : undefined;
}

function replacePlaceholders(text: string, params?: Record<string, string | number>): string {
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

function resolveTranslation(data: TranslationData | undefined, key: string): unknown {
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
  if (key.startsWith("qa.")) {
    const qaData = data.qa;
    if (!qaData) return undefined;
    const nestedkey = key.replace("qa.", "");
    if (nestedkey === "category") {
      return qaData.category;
    }
    return resolveNested(qaData, nestedkey);
  }
  return undefined;
}

export function t(
  key: string,
  params?: Record<string, string | number>,
  langOverride?: string,
): string {
  const lang = langOverride && languages[langOverride] ? langOverride : getCurrentLang();
  const result =
    resolveTranslation(languages[lang], key) ||
    resolveTranslation(languages[FALLBACK_LANG], key) ||
    fallbackText(key);

  if (typeof result === "string") {
    return replacePlaceholders(result, params);
  }
  return key;
}

function fallbackText(key: string): string {
  return key;
}

export { fallbackText };

export function tObject(key: string, langOverride?: string): unknown {
  const lang = langOverride && languages[langOverride] ? langOverride : getCurrentLang();
  const result =
    resolveTranslation(languages[lang], key) || resolveTranslation(languages[FALLBACK_LANG], key);
  return result;
}

export function tHtml(
  key: string,
  params?: Record<string, string | number>,
  langOverride?: string,
): string {
  const text = t(key, params, langOverride);
  return text.replace(/\r?\n/g, "<br>");
}

const DAYS_PER_MONTH = 30;
const MONTHS_PER_YEAR = 12;
const DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR;

function yearPluralKey(years: number, lang: string): string {
  if (lang === "ru" || lang === "be") {
    if (years % 10 === 1 && years % 100 !== 11) return "texts.duration_year_one";
    if (years % 10 >= 2 && years % 10 <= 4 && (years % 100 < 12 || years % 100 > 14)) {
      return "texts.duration_year_few";
    }
    return "texts.duration_year_many";
  }
  if (lang === "pl") {
    if (years === 1) return "texts.duration_year_one";
    if (years % 10 >= 2 && years % 10 <= 4 && (years % 100 < 12 || years % 100 > 14)) {
      return "texts.duration_year_few";
    }
    return "texts.duration_year_many";
  }
  return years === 1 ? "texts.duration_year_one" : "texts.duration_year_many";
}

export function formatTariffDuration(days: number, langOverride?: string): string {
  const lang = langOverride && languages[langOverride] ? langOverride : getCurrentLang();
  const totalDays = Math.max(0, Math.trunc(days) || 0);
  if (totalDays > 0 && totalDays % DAYS_PER_YEAR === 0) {
    const years = totalDays / DAYS_PER_YEAR;
    return t(yearPluralKey(years, lang), { years }, lang);
  }
  return t("texts.duration_days", { days: totalDays }, lang);
}

export function formatTariffTraffic(
  value: number,
  perMonth: boolean,
  langOverride?: string,
): string {
  if (value <= 0) return t("texts.unlimited", undefined, langOverride);
  const TB = 1024;
  if (value >= TB && value % TB === 0) {
    const key = perMonth ? "texts.traffic_tb_per_month" : "texts.traffic_tb";
    return t(key, { value: value / TB }, langOverride);
  }
  const key = perMonth ? "texts.traffic_gb_per_month" : "texts.traffic_gb";
  return t(key, { value }, langOverride);
}

export function getLanguageDisplayName(code: string): string {
  const data = languages[code];
  return data?.meta?.name || code;
}

export function getAvailableLanguages(): string[] {
  return Object.keys(languages);
}

export async function initI18n(): Promise<void> {
  return;
}
