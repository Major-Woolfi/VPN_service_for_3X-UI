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
  setCurrentLang as setCurrentLangGlobal,
} from "@/lib/i18n";

interface LanguageContextType {
  lang: string;
  setLang: (lang: string) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  tHtml: (key: string, params?: Record<string, string | number>) => string;
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
  // Seed from the server-resolved language so SSR markup and the first
  // client render match; otherwise hydration would flash the fallback.
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
    (key: string, params?: Record<string, string | number>) => {
      return translate(key, params, lang);
    },
    [lang],
  );

  const tHtml = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      return translateHtml(key, params, lang);
    },
    [lang],
  );

  return (
    <LanguageContext.Provider
      value={{ lang, setLang: setLangWrapper, t, tHtml }}
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
