"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import {
  getCurrentLang,
  t as translate,
  tHtml as translateHtml,
  tObject as translateObject,
  setCurrentLang as setCurrentLangGlobal,
} from "@/lib/i18n";

interface LanguageContextType {
  lang: string;
  setLang: (lang: string) => void;
  t: (key: string, params?: Record<string, string | number>, langOverride?: string) => string;
  tHtml: (key: string, params?: Record<string, string | number>, langOverride?: string) => string;
  tObject: (key: string, langOverride?: string) => unknown;
}

const LanguageContext = createContext<LanguageContextType | undefined>(
  undefined,
);

export function LanguageProvider({
  children,
  initialLang,
}: {
  children: ReactNode;
  initialLang?: string;
}) {

  const [lang, setLang] = useState(() => initialLang || getCurrentLang());

  useEffect(() => {
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<{ lang: string }>;
      if (customEvent.detail?.lang) {
        setLang(customEvent.detail.lang);
      }
    };
    window.addEventListener("vpn-languagechange", handler);
    return () => window.removeEventListener("vpn-languagechange", handler);
  }, []);

  const setLangWrapper = useCallback((newLang: string) => {
    if (setCurrentLangGlobal(newLang)) {
      setLang(newLang);
    }
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>, langOverride?: string) => {
      return translate(key, params, langOverride || lang);
    },
    [lang],
  );

  const tHtml = useCallback(
    (key: string, params?: Record<string, string | number>, langOverride?: string) => {
      return translateHtml(key, params, langOverride || lang);
    },
    [lang],
  );

  const tObject = useCallback(
    (key: string, langOverride?: string) => {
      return translateObject(key, langOverride || lang);
    },
    [lang],
  );

  return (
    <LanguageContext.Provider
      value={{ lang, setLang: setLangWrapper, t, tHtml, tObject }}
    >
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
