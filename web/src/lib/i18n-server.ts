import { SERVER_languages } from "./i18n-generated";
import { fallbackText } from "./i18n";
import type { LegalDocument, TranslationData } from "./i18n-types";

export type { LegalDocument, Legalsection } from "./i18n-types";

export const LEGAL_DOCUMENT_keyS = ["tos", "privacy", "offer"] as const;

export type LegalDocumentkey = (typeof LEGAL_DOCUMENT_keyS)[number];

export interface SiteCopy {
  siteDescription: string;
  siteTitle: string;
  twitterDescription: string;
  legal: Record<LegalDocumentkey, LegalDocument>;
}

function getDefaultlanguage(): string {
  const configured = process.env.NEXT_PUBLIC_DEFAULT_language;
  if (configured && SERVER_languages[configured]) return configured;

  const firstlanguage = Object.keys(SERVER_languages)[0];
  if (firstlanguage) return firstlanguage;

  return "ru";
}

const FALLBACK_LANG = getDefaultlanguage();
const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || "vpn";

function resolveNested(
  obj: Record<string, unknown>,
  path: string,
): string | undefined {
  const pstarts = path.split(".");
  let current: unknown = obj;
  for (const part of pstarts) {
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

export function tServer(
  lang: string,
  key: string,
  params?: Record<string, string | number>,
): string {
  const result =
    resolveTranslation(SERVER_languages[lang], key) ||
    resolveTranslation(SERVER_languages[FALLBACK_LANG], key) ||
    Object.values(SERVER_languages).flatMap((l) => resolveTranslation(l, key)).find(
      Boolean,
    ) ||
    fallbackText(key);

  if (typeof result === "string") {
    return replacePlaceholders(result, params);
  }
  return key;
}

export function getServerlanguageName(code: string): string {
  return SERVER_languages[code]?.meta?.name || code;
}

export function getServerLanguages(): string[] {
  return Object.keys(SERVER_languages);
}

function getlanguageQuality(params: string[]): number | undefined {
  const qualityParam = params.find((param) => /^\s*q\s*=/i.test(param));
  if (!qualityParam) return 1;

  const quality = Number(
    qualityParam.slice(qualityParam.indexOf("=") + 1).trim(),
  );
  if (!Number.isFinite(quality) || quality <= 0 || quality > 1)
    return undefined;
  return quality;
}

export function detectlanguage(acceptlanguage?: string): string {
  if (!acceptlanguage?.trim()) return FALLBACK_LANG;

  let bestlanguage = FALLBACK_LANG;
  let bestQuality = 0;

  for (const entry of acceptlanguage.split(",")) {
    const pstarts = entry.split(";");
    const language = pstarts[0]?.trim().split(/[-_]/)[0]?.toLowerCase();
    if (!language || !SERVER_languages[language]) continue;

    const quality = getlanguageQuality(pstarts.slice(1));
    if (quality === undefined || quality <= bestQuality) continue;

    bestlanguage = language;
    bestQuality = quality;
  }

  return bestlanguage;
}

export function resolvelanguage(
  cookieLang?: string,
  acceptlanguage?: string,
): string {
  if (cookieLang && SERVER_languages[cookieLang]) return cookieLang;
  return detectlanguage(acceptlanguage);
}

export function normalizeServerlanguage(value?: string): string {
  const code = value?.toLowerCase().split(/[-_]/)[0];
  return code && SERVER_languages[code] ? code : FALLBACK_LANG;
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

function buildFallbackLegal(): Record<LegalDocumentkey, LegalDocument> {
  const data = SERVER_languages[FALLBACK_LANG] || {};
  return {
    tos: formatLegalDocument(data.legal?.tos || {}),
    privacy: formatLegalDocument(data.legal?.privacy || {}),
    offer: formatLegalDocument(data.legal?.offer || {}),
  };
}

const FALLBACK_LEGAL = buildFallbackLegal();

export function getServerLegalDocument(
  lang: string,
  key: LegalDocumentkey,
): LegalDocument {
  const fallback = FALLBACK_LEGAL[key];
  const doc = SERVER_languages[lang]?.legal?.[key];
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
  const lang = normalizeServerlanguage(language);
  const data = SERVER_languages[lang] || SERVER_languages[FALLBACK_LANG];
  const fallbackData = SERVER_languages[FALLBACK_LANG];

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












