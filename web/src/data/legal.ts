import { SERVER_LANGUAGES } from "../lib/i18n-generated";
import type { TranslationData } from "../lib/i18n-types";

const SITE_NAME = process.env.NEXT_PUBLIC_VPN_NAME || "VPN";
const SUPPORTED_LANGUAGES = Object.keys(SERVER_LANGUAGES);

function getDefaultLanguage(): string {
  const configured = process.env.NEXT_PUBLIC_DEFAULT_LANGUAGE;
  if (configured && SERVER_LANGUAGES[configured]) return configured;

  const firstLanguage = SUPPORTED_LANGUAGES[0];
  if (!firstLanguage) throw new Error("No languages configured");
  return firstLanguage;
}

const FALLBACK_LANGUAGE = getDefaultLanguage();

function formatTemplate(text: string): string {
  return text
    .replace(/\{siteName\}/g, SITE_NAME)
    .replace(/\{vpnName\}/g, SITE_NAME);
}

export interface LegalSection {
  title: string;
  content: string;
}

export interface LegalDocument {
  title: string;
  subtitle: string;
  effectiveDate: string;
  sections: LegalSection[];
}

export interface SiteCopy {
  siteDescription: string;
  siteTitle: string;
  twitterDescription: string;
  legal: {
    tos: LegalDocument;
    privacy: LegalDocument;
    offer: LegalDocument;
  };
}

function getLangData(lang: string): TranslationData | undefined {
  return SERVER_LANGUAGES[lang] || SERVER_LANGUAGES[FALLBACK_LANGUAGE];
}

function toLegalDocument(
  doc: Partial<LegalDocument> | undefined,
): LegalDocument {
  return {
    title: doc?.title || "",
    subtitle: doc?.subtitle || "",
    effectiveDate: doc?.effectiveDate || "",
    sections: Array.isArray(doc?.sections)
      ? doc.sections.map((section) => ({
          title: section.title || "",
          content: section.content || "",
        }))
      : [],
  };
}

function ensureLegal(
  doc: Partial<LegalDocument>,
  fallback: LegalDocument,
): LegalDocument {
  if (!doc || !doc.title) return fallback;
  return {
    title: formatTemplate(doc.title || fallback.title),
    subtitle: formatTemplate(doc.subtitle || fallback.subtitle),
    effectiveDate: doc.effectiveDate || fallback.effectiveDate,
    sections:
      Array.isArray(doc.sections) && doc.sections.length > 0
        ? doc.sections.map((s: Partial<LegalSection>) => ({
            title: formatTemplate(s.title || ""),
            content: formatTemplate(s.content || "").replace(/\n/g, "<br>"),
          }))
        : fallback.sections,
  };
}

function getRawCopy(lang: string): Partial<SiteCopy> {
  const data = getLangData(lang);
  if (!data) return {};

  const texts = data.texts;
  const legal = data.legal || {};

  return {
    siteDescription: formatTemplate(texts.siteDescription || ""),
    siteTitle: formatTemplate(texts.siteTitle || ""),
    twitterDescription: formatTemplate(texts.twitterDescription || ""),
    legal: {
      tos: legal.tos || {},
      privacy: legal.privacy || {},
      offer: legal.offer || {},
    },
  };
}

const FALLBACK_RAW = getRawCopy(FALLBACK_LANGUAGE);
const FALLBACK: SiteCopy = {
  siteDescription: FALLBACK_RAW.siteDescription || "",
  siteTitle: FALLBACK_RAW.siteTitle || "",
  twitterDescription: FALLBACK_RAW.twitterDescription || "",
  legal: {
    tos: toLegalDocument(FALLBACK_RAW.legal?.tos),
    privacy: toLegalDocument(FALLBACK_RAW.legal?.privacy),
    offer: toLegalDocument(FALLBACK_RAW.legal?.offer),
  },
};

export function getSiteCopy(language?: string): SiteCopy {
  const normalized = language
    ? normalizeSiteLanguage(language)
    : FALLBACK_LANGUAGE;
  const raw = getRawCopy(normalized);

  return {
    siteDescription: raw.siteDescription || FALLBACK.siteDescription,
    siteTitle: raw.siteTitle || FALLBACK.siteTitle,
    twitterDescription: raw.twitterDescription || FALLBACK.twitterDescription,
    legal: {
      tos: ensureLegal(raw.legal?.tos || {}, FALLBACK.legal.tos),
      privacy: ensureLegal(raw.legal?.privacy || {}, FALLBACK.legal.privacy),
      offer: ensureLegal(raw.legal?.offer || {}, FALLBACK.legal.offer),
    },
  };
}

export function normalizeSiteLanguage(value?: string): string {
  const code = value?.toLowerCase().split("-")[0];
  return code && SUPPORTED_LANGUAGES.includes(code) ? code : FALLBACK_LANGUAGE;
}
