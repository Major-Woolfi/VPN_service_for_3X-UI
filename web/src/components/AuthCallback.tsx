"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useLanguage } from "@/contexts/LanguageContext";
import { pollTelegramAuth, TELEGRAM_POLL_INTERVAL_MS, TELEGRAM_POLL_TIMEOUT_MS } from "@/lib/api";

type AuthCallbackStatus = "idle" | "processing" | "error";

export default function AuthCallback() {
  const { t } = useLanguage();

  const searchParams = useSearchParams();
  const state = searchParams?.get("state") || null;
  const [status, setStatus] = useState<AuthCallbackStatus>(state ? "processing" : "idle");
  const processedRef = useRef(false);
  const inFlightRef = useRef(false);

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
        // sessionStorage может быть недоступен - используем /profile.
      }
    }
    return "/profile";
  }, []);

  useEffect(() => {
    if (!state || processedRef.current) return;
    processedRef.current = true;

    let cancelled = false;
    const timers: {
      interval?: ReturnType<typeof setInterval>;
      timeout?: ReturnType<typeof setTimeout>;
    } = {};
    const stopPolling = () => {
      if (timers.interval !== undefined) clearInterval(timers.interval);
      if (timers.timeout !== undefined) clearTimeout(timers.timeout);
    };
    const fail = (reason: string) => {
      if (cancelled) return;
      stopPolling();
      setStatus("error");
      window.location.replace(`/login?reason=${reason}`);
    };

    const poll = async () => {
      if (cancelled || inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const res = await pollTelegramAuth(state);
        if (cancelled) return;
        if (res.status === "completed") {
          window.location.replace(resolveTarget(state));
        } else if (res.status === "timeout" || res.status === "expired") {
          fail("auth_timeout");
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Telegram auth polling failed", err);
          fail("auth_error");
        }
      } finally {
        inFlightRef.current = false;
      }
    };

    void poll();
    timers.interval = setInterval(() => void poll(), TELEGRAM_POLL_INTERVAL_MS);
    timers.timeout = setTimeout(() => fail("auth_timeout"), TELEGRAM_POLL_TIMEOUT_MS);

    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [resolveTarget, state]);

  if (status === "idle") return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
        fontSize: "14px",
        zIndex: "var(--z-overlay)",
      }}
    >
      {status === "processing" ? t("texts.authenticating") : t("texts.auth_error")}
    </div>
  );
}
