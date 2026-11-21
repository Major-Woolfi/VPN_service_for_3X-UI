"use client";

import { useEffect } from "react";

export default function ThemeInit() {
  useEffect(() => {
    try {
      const stored = localStorage.getItem("vpn_theme");
      const theme =
        stored === "light" || stored === "dark"
          ? stored
          : window.matchMedia?.("(prefers-color-scheme: light)")?.matches
            ? "light"
            : "dark";
      document.documentElement.classList.remove("theme-dark", "theme-light");
      document.documentElement.classList.add(`theme-${theme}`);
      document.documentElement.style.colorScheme = theme;
      const colorSchemeMeta = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
      if (colorSchemeMeta) colorSchemeMeta.content = theme;
    } catch {
      document.documentElement.classList.add("theme-dark");
    }
  }, []);

  return null;
}
