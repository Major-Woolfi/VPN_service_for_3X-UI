import { LANGUAGES } from '../lib/i18n-generated';
import { SERVER_LANGUAGES } from '../lib/i18n-generated';
import type { TranslationData } from '../lib/i18n-types';

const SITE_NAME = process.env.NEXT_PUBLIC_VPN_NAME || 'VPN';

function formatTemplate(text: string): string {
  return text.replace(/\{siteName\}/g, SITE_NAME).replace(/\{vpnName\}/g, SITE_NAME);
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

function getLangData(lang: string): TranslationData {
  return (SERVER_LANGUAGES[lang] || LANGUAGES[lang] || LANGUAGES['ru']) as TranslationData;
}

function ensureLegal(doc: Partial<LegalDocument>, fallback: LegalDocument): LegalDocument {
  if (!doc || !doc.title) return fallback;
  return {
    title: formatTemplate(doc.title || fallback.title),
    subtitle: formatTemplate(doc.subtitle || fallback.subtitle),
    effectiveDate: doc.effectiveDate || fallback.effectiveDate,
    sections: Array.isArray(doc.sections) && doc.sections.length > 0
      ? doc.sections.map((s: Partial<LegalSection>) => ({
          title: formatTemplate(s.title || ''),
          content: formatTemplate(s.content || '').replace(/\n/g, '<br>'),
        }))
      : fallback.sections,
  }
}

function getRawCopy(lang: string): Partial<SiteCopy> {
  const data = getLangData(lang);
  const texts = data.texts;
  const legal = data.legal || {};

  return {
    siteDescription: formatTemplate(texts.siteDescription || ''),
    siteTitle: formatTemplate(texts.siteTitle || ''),
    twitterDescription: formatTemplate(texts.twitterDescription || ''),
    legal: {
      tos: legal.tos || {},
      privacy: legal.privacy || {},
      offer: legal.offer || {},
    },
  };
}

const FALLBACK = getRawCopy('ru') as SiteCopy;

export function getSiteCopy(language?: string): SiteCopy {
  const normalized = language || 'ru';
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

export function normalizeSiteLanguage(value?: string): 'ru' | 'en' | 'pl' | 'zh' | 'be' | 'de' | 'ja' {
  const code = value?.toLowerCase().split('-')[0];
  return (code && ['ru', 'en', 'pl', 'zh', 'be', 'de', 'ja'].includes(code) ? code : 'ru') as 'ru' | 'en' | 'pl' | 'zh' | 'be' | 'de' | 'ja';
}
