const OPENGRAPH_LOCALES: Record<string, string> = {
  ru: "ru_RU",
  en: "en_US",
  de: "de_DE",
  be: "be_BY",
  ja: "ja_JP",
  pl: "pl_PL",
  zh: "zh_CN",
};

export function getOpenGraphLocale(lang: string): string {
  return OPENGRAPH_LOCALES[lang] || `${lang}_${lang.toUpperCase()}`;
}
