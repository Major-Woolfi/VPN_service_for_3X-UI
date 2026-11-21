"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useCopyToClipboard() {
  const [copied, setCopied] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleReset = useCallback((text: string) => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
    }
    setCopied(text);
    timeoutRef.current = setTimeout(() => {
      timeoutRef.current = null;
      setCopied(null);
    }, 2000);
  }, []);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, []);

  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        scheduleReset(text);
      } catch {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
        scheduleReset(text);
      }
    },
    [scheduleReset],
  );

  return { copy, copied };
}
