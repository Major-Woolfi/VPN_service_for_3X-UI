"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useEffect,
  type ReactNode,
} from "react";

type Theme = "dark" | "light";

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: "dark" | "light") => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_KEY = "vpn_theme";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem(THEME_KEY) as Theme | null;
        if (stored === "light" || stored === "dark") return stored;
      } catch {}
      if (window.matchMedia("(prefers-color-scheme: light)").matches) return "light";
    }
    return "dark";
  });

  useEffect(() => {
    document.documentElement.classList.remove("theme-dark", "theme-light");
    document.documentElement.classList.add(`theme-${theme}`);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {}
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  const value = useMemo(() => ({ theme, setTheme, toggleTheme }), [theme, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
