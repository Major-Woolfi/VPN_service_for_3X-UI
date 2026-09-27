"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  pollTelegramAuth,
  TELEGRAM_POLL_INTERVAL_MS,
  TELEGRAM_POLL_TIMEOUT_MS,
} from "@/lib/api";

type AuthCallbackStatus = "idle" | "processing" | "error";

function readState(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("state");
}

export default function AuthCallback() {
  const { t } = useLanguage();
  const [state, setState] = useState<string | null>(null);
  const [status, setStatus] = useState<AuthCallbackStatus>("idle");
  const processedRef = useRef(false);

  const resolveTarget = useCallback((authState: string | null) => {
    if (typeof window === "undefined") return "/profile";

    const params = new URLSearchParams(window.location.search);
    const next = params.get("next");
    if (next && next.startsWith("/") && !next.startsWith("//")) return next;

    if (authState) {
      try {
        const saved = sessionStorage.getItem(`vpn_auth_next_${authState}`);
        if (saved && saved.startsWith("/") && !saved.startsWith("//")) {
          sessionStorage.removeItem(`vpn_auth_next_${authState}`);
          return saved;
        }
      } catch {
        // ignore
      }
    }
    return "/profile";
  }, []);

  useEffect(() => {
    const current = readState();
    if (!current) return;
    setState(current);
    setStatus("processing");
  }, []);

  useEffect(() => {
    if (!state || processedRef.current) return;
    processedRef.current = true;

    let cancelled = false;
    const fail = (reason: string) => {
      if (cancelled) return;
      setStatus("error");
      window.location.replace(`/login?reason=${reason}`);
    };

    const poll = async () => {
      try {
        const res = await pollTelegramAuth(state);
        if (cancelled) return;
        if (res.status === "completed") {
          window.location.replace(resolveTarget(state));
        } else if (res.status === "timeout" || res.status === "expired") {
          fail("auth_timeout");
        }
      } catch {
        // игнорируем отдельные сбои опроса
      }
    };

    void poll();
    const interval = setInterval(poll, TELEGRAM_POLL_INTERVAL_MS);
    const timeout = setTimeout(() => {
      clearInterval(interval);
      fail("auth_timeout");
    }, TELEGRAM_POLL_TIMEOUT_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [resolveTarget, state]);

  if (status === "idle") return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
        fontSize: "14px",
        zIndex: 9999,
      }}
    >
      {status === "processing"
        ? t("texts.authenticating")
        : t("texts.auth_error")}
    </div>
  );
}
