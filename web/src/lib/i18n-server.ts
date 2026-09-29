// Серверный i18n - переводы импортируются из auto-generated файла
// Используется в Server Components; fallback берётся из доступных языков

import { SERVER_LANGUAGES } from "./i18n-generated";
import type { LegalDocument, TranslationData } from "./i18n-types";

export type { LegalDocument, LegalSection } from "./i18n-types";

export const LEGAL_DOCUMENT_KEYS = ["tos", "privacy", "offer"] as const;

export type LegalDocumentKey = (typeof LEGAL_DOCUMENT_KEYS)[number];

export interface SiteCopy {
  siteDescription: string;
  siteTitle: string;
  twitterDescription: string;
  legal: Record<LegalDocumentKey, LegalDocument>;
}

function getDefaultLanguage(): string {
  const configured = process.env.NEXT_PUBLIC_DEFAULT_LANGUAGE;
  if (configured && SERVER_LANGUAGES[configured]) return configured;

  const firstLanguage = Object.keys(SERVER_LANGUAGES)[0];
  if (!firstLanguage) throw new Error("No languages configured");
  return firstLanguage;
}

const FALLBACK_LANG = getDefaultLanguage();
const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || "vpn";

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
  // Глобальная замена {vpnName} и {siteName}
  let result = text.replace(/\{vpnName\}/g, VPN_NAME);
  result = result.replace(/\{siteName\}/g, VPN_NAME);

  // Замена пользовательских плейсхолдеров
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

export function tServer(
  lang: string,
  key: string,
  params?: Record<string, string | number>,
): string {
  const text =
    resolveTranslation(SERVER_LANGUAGES[lang], key) ||
    resolveTranslation(SERVER_LANGUAGES[FALLBACK_LANG], key) ||
    key;

  return replacePlaceholders(text, params);
}

export function getServerLanguageName(code: string): string {
  return SERVER_LANGUAGES[code]?.meta?.name || code;
}

export function getServerLanguages(): string[] {
  return Object.keys(SERVER_LANGUAGES);
}

function getLanguageQuality(params: string[]): number | undefined {
  const qualityParam = params.find((param) => /^\s*q\s*=/i.test(param));
  if (!qualityParam) return 1;

  const quality = Number(
    qualityParam.slice(qualityParam.indexOf("=") + 1).trim(),
  );
  if (!Number.isFinite(quality) || quality <= 0 || quality > 1)
    return undefined;
  return quality;
}

export function detectLanguage(acceptLanguage?: string): string {
  if (!acceptLanguage?.trim()) return FALLBACK_LANG;

  let bestLanguage = FALLBACK_LANG;
  let bestQuality = 0;

  for (const entry of acceptLanguage.split(",")) {
    const parts = entry.split(";");
    const language = parts[0]?.trim().split(/[-_]/)[0]?.toLowerCase();
    if (!language || !SERVER_LANGUAGES[language]) continue;

    const quality = getLanguageQuality(parts.slice(1));
    if (quality === undefined || quality <= bestQuality) continue;

    bestLanguage = language;
    bestQuality = quality;
  }

  return bestLanguage;
}

export function resolveLanguage(
  cookieLang?: string,
  acceptLanguage?: string,
): string {
  if (cookieLang && SERVER_LANGUAGES[cookieLang]) return cookieLang;
  return detectLanguage(acceptLanguage);
}

export function normalizeServerLanguage(value?: string): string {
  const code = value?.toLowerCase().split(/[-_]/)[0];
  return code && SERVER_LANGUAGES[code] ? code : FALLBACK_LANG;
}

function formatLegalDocument(doc: Partial<LegalDocument>): LegalDocument {
  return {
    title: replacePlaceholders(doc.title || ""),
    subtitle: replacePlaceholders(doc.subtitle || ""),
    effectiveDate: doc.effectiveDate || "",
    sections: Array.isArray(doc.sections)
      ? doc.sections.map((section) => ({
          title: replacePlaceholders(section.title || ""),
          content: replacePlaceholders(section.content || "").replace(
            /\r?\n/g,
            "<br>",
          ),
        }))
      : [],
  };
}

function buildFallbackLegal(): Record<LegalDocumentKey, LegalDocument> {
  const data = SERVER_LANGUAGES[FALLBACK_LANG];
  return {
    tos: formatLegalDocument(data.legal?.tos || {}),
    privacy: formatLegalDocument(data.legal?.privacy || {}),
    offer: formatLegalDocument(data.legal?.offer || {}),
  };
}

const FALLBACK_LEGAL = buildFallbackLegal();

export function getServerLegalDocument(
  lang: string,
  key: LegalDocumentKey,
): LegalDocument {
  const fallback = FALLBACK_LEGAL[key];
  const doc = SERVER_LANGUAGES[lang]?.legal?.[key];
  if (!doc?.title) return fallback;

  const formatted = formatLegalDocument(doc);
  return {
    title: formatted.title || fallback.title,
    subtitle: formatted.subtitle || fallback.subtitle,
    effectiveDate: formatted.effectiveDate || fallback.effectiveDate,
    sections:
      formatted.sections.length > 0 ? formatted.sections : fallback.sections,
  };
}

export function getServerSiteCopy(language?: string): SiteCopy {
  const lang = normalizeServerLanguage(language);
  const data = SERVER_LANGUAGES[lang] || SERVER_LANGUAGES[FALLBACK_LANG];
  const fallbackData = SERVER_LANGUAGES[FALLBACK_LANG];

  const pick = (key: string): string => {
    const value = resolveTranslation(data, key);
    if (value !== undefined) return replacePlaceholders(value);
    const fallbackValue = resolveTranslation(fallbackData, key);
    return fallbackValue !== undefined
      ? replacePlaceholders(fallbackValue)
      : "";
  };

  return {
    siteDescription: pick("texts.siteDescription"),
    siteTitle: pick("texts.siteTitle"),
    twitterDescription: pick("texts.twitterDescription"),
    legal: {
      tos: getServerLegalDocument(lang, "tos"),
      privacy: getServerLegalDocument(lang, "privacy"),
      offer: getServerLegalDocument(lang, "offer"),
    },
  };
}
