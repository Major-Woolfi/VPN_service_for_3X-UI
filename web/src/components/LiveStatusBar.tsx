"use client";

import { useEffect, useState, useRef } from "react";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  ApiError,
  HEALTH_POLL_INTERVAL_MS,
  getHealth,
} from "@/lib/api";

type Health = { status: string; version: string } | null;

export default function LiveStatusBar() {
  const [health, setHealth] = useState<Health>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const { t, lang } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      if (typeof document !== "undefined" && document.hidden) return;

      try {
        const data = await getHealth();
        if (!cancelled) {
          setHealth(data);
          setOnline(true);
          setLastUpdate(new Date());
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 429) return;
        setOnline(false);
        console.error("[LiveStatusBar] health check Error:", err);
      }
    };

    check();
    const interval = setInterval(check, HEALTH_POLL_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (!document.hidden) {
        check();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  if (online === null) return null;

  return (
    <div
      ref={containerRef}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        padding: "6px 12px",
        background: "var(--bg-tertiary)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-sm)",
        fontSize: "12px",
        color: "var(--text-secondary)",
      }}
    >
      <span
        style={{
          width: "8px",
          height: "8px",
          borderRadius: "50%",
          background: online ? "var(--success)" : "var(--danger)",
          boxShadow: online
            ? "0 0 6px var(--success)"
            : "0 0 6px var(--danger)",
          animation: online ? "pulse 2s infinite" : "none",
        }}
      />
      <span>{online ? t("texts.api_online") : t("texts.api_offline")}</span>
      {health?.version && (
        <span style={{ color: "var(--text-muted)" }}>v{health.version}</span>
      )}
      {lastUpdate && (
        <span style={{ color: "var(--text-muted)" }}>
          ·{" "}
          {lastUpdate.toLocaleTimeString(lang, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </span>
      )}
    </div>
  );
}


