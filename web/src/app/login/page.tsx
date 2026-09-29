"use client";

import Header from "@/components/Header";
import Link from "next/link";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  loginUser,
  startTelegramAuth,
  pollTelegramAuth,
  clearStoredUser,
  TELEGRAM_POLL_INTERVAL_MS,
  TELEGRAM_POLL_TIMEOUT_MS,
} from "@/lib/api";
import { useLanguage } from "@/contexts/LanguageContext";

const POLL_INTERVAL = TELEGRAM_POLL_INTERVAL_MS;
const POLL_TIMEOUT = TELEGRAM_POLL_TIMEOUT_MS;

function safeNextPath(): string {
  if (typeof window === "undefined") return "/profile";
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//"))
    return "/profile";
  return next;
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useLanguage();
  const [method, setMethod] = useState<"password" | "telegram">("password");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tgWaiting, setTgWaiting] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reason = searchParams?.get("reason") || "";
  const nextPath = safeNextPath();

  // Сообщение по ?reason= - производное значение от URL, а не состояние.
  const reasonError =
    reason === "session_expired"
      ? t("texts.session_expired")
      : reason === "banned"
        ? t("texts.account_banned")
        : reason === "auth_expired"
          ? t("texts.auth_error")
          : reason === "auth_timeout"
            ? t("texts.login_timeout")
            : "";
  const shownError = error || reasonError;

  // Сервер принудительно разлогинил (истёкшая сессия) и попросил
  // почистить клиентский кэш через vpn_clear_cache. Cookie одноразовая,
  // поэтому читаем её до первого рендера.
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (!/(^|;\s*)vpn_clear_cache=1(;|$)/.test(document.cookie)) return;
    clearStoredUser();
    document.cookie = "vpn_clear_cache=; path=/; max-age=0; samesite=lax";
  }, []);

  const finish = useCallback(() => {
    setLoading(false);
    setTgWaiting(false);
    // refresh() перезапрашивает серверный layout, который ставит initialUser
    // уже с профилем - редирект без "мигания" загрузки.
    router.refresh();
    router.replace(nextPath);
  }, [router, nextPath]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    setTgWaiting(false);
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const startPolling = useCallback(
    (state: string) => {
      stopPolling();
      setTgWaiting(true);
      let elapsed = 0;
      pollIntervalRef.current = setInterval(async () => {
        try {
          const res = await pollTelegramAuth(state);
          if (res.status === "completed") {
            stopPolling();
            finish();
          } else if (res.status === "timeout" || res.status === "expired") {
            stopPolling();
            setError(t("texts.login_timeout"));
          }
        } catch {
          // игнорируем отдельные сбои опроса
        }
        elapsed += POLL_INTERVAL;
        if (elapsed >= POLL_TIMEOUT) {
          stopPolling();
          setError(t("texts.login_timeout"));
        }
      }, POLL_INTERVAL);

      pollTimeoutRef.current = setTimeout(() => stopPolling(), POLL_TIMEOUT);
    },
    [stopPolling, finish, t],
  );

  const handleTelegramLogin = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await startTelegramAuth();
      if (!res?.url || !res.state) {
        setError(t("texts.login_error"));
        return;
      }
      if (nextPath !== "/profile") {
        try {
          sessionStorage.setItem(`vpn_auth_next_${res.state}`, nextPath);
        } catch {
          // ignore
        }
      }
      window.open(res.url, "_blank", "noopener,noreferrer");
      startPolling(res.state);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.login_error"));
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await loginUser({ username: username.trim(), password });
      finish();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.login_error"));
      setLoading(false);
    }
  };

  return (
    <>
      <Header currentPage="/login" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.login_title")}</h1>
              <p className="profile-username">{t("texts.login_subtitle")}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div className="flex flex-col gap-4 mt-5">
                <div className="flex gap-2 mb-2">
                  <button
                    onClick={() => setMethod("password")}
                    className={
                      "flex-1 px-3 py-3.5 rounded-md text-sm cursor-pointer border transition-colors " +
                      (method === "password"
                        ? "bg-[var(--accent-glow)] border-[var(--accent)] text-[var(--text-primary)]"
                        : "border-[var(--border-color)] text-[var(--text-primary)] bg-transparent")
                    }
                  >
                    {t("buttons.password_login")}
                  </button>
                  <button
                    onClick={() => setMethod("telegram")}
                    className={
                      "flex-1 px-3 py-3.5 rounded-md text-sm cursor-pointer border transition-colors " +
                      (method === "telegram"
                        ? "bg-[var(--accent-glow)] border-[var(--accent)] text-[var(--text-primary)]"
                        : "border-[var(--border-color)] text-[var(--text-primary)] bg-transparent")
                    }
                  >
                    {t("buttons.telegram_login")}
                  </button>
                </div>

                {shownError && (
                  <div className="error-message">{shownError}</div>
                )}

                {method === "password" ? (
                  <form
                    onSubmit={handlePasswordLogin}
                    className="flex flex-col gap-3"
                    noValidate
                  >
                    <input
                      type="text"
                      placeholder={t("texts.username")}
                      className="faq-search-input"
                      value={username}
                      onChange={(e) =>
                        setUsername(e.target.value.replace(/[<>"'&]/g, ""))
                      }
                      autoComplete="username"
                      required
                    />
                    <input
                      type="password"
                      placeholder={t("texts.password")}
                      className="faq-search-input"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password"
                      required
                    />
                    <button
                      type="submit"
                      className="button w-full"
                      disabled={loading}
                    >
                      {loading ? t("texts.waiting") : t("buttons.login")}
                    </button>
                  </form>
                ) : (
                  <div className="flex flex-col gap-3">
                    <button
                      onClick={handleTelegramLogin}
                      className="button"
                      disabled={loading}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "8px",
                        textDecoration: "none",
                      }}
                    >
                      <svg
                        width="20"
                        height="20"
                        fill="currentColor"
                        viewBox="0 0 30 30"
                      >
                        <path d="m20.665 3.717-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l.002.001-.314 4.692c.46 0.663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.434z" />
                      </svg>
                      {t("buttons.telegram_login")}
                    </button>
                    {tgWaiting && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: "8px",
                          padding: "12px",
                          background: "rgba(59, 130, 246, 0.1)",
                          border: "1px solid rgba(59, 130, 246, 0.3)",
                          borderRadius: "var(--radius-sm)",
                          color: "var(--text-primary)",
                          fontSize: "14px",
                        }}
                      >
                        <div
                          style={{
                            width: "16px",
                            height: "16px",
                            border: "2px solid var(--border-color)",
                            borderTopColor: "var(--accent)",
                            borderRadius: "50%",
                            animation: "spin 0.8s linear infinite",
                          }}
                        />
                        {t("texts.telegram_waiting")}
                      </div>
                    )}
                    <p className="text-center text-secondary text-sm">
                      {t("texts.telegram_login_hint")}
                    </p>
                  </div>
                )}

                <p className="text-center text-secondary text-sm">
                  {t("texts.no_account")}{" "}
                  <Link href="/register" className="font-semibold">
                    {t("buttons.register")}
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
