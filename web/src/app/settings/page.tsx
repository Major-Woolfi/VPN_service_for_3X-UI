"use client";

import Header from "@/components/Header";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import {
  changeLanguage,
  changePassword,
  startTelegramLink,
  pollTelegramAuth,
  TELEGRAM_POLL_INTERVAL_MS,
  TELEGRAM_POLL_TIMEOUT_MS,
} from "@/lib/api";
import {
  setCurrentLang,
  getAvailableLanguages,
  getLanguageDisplayName,
} from "@/lib/i18n";
import { useLanguage } from "@/contexts/LanguageContext";

const link_POLL_INTERVAL = TELEGRAM_POLL_INTERVAL_MS;
const link_POLL_TIMEOUT = TELEGRAM_POLL_TIMEOUT_MS;

const MoonIcon = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

const SunIcon = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="12" r="5" />
    <line x1="12" y1="1" x2="12" y2="3" />
    <line x1="12" y1="21" x2="12" y2="23" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="1" y1="12" x2="3" y2="12" />
    <line x1="21" y1="12" x2="23" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

export default function SettingsPage() {
  const router = useRouter();
  const {
    loading: authLoading,
    logout,
    refreshUser,
    user: authUser,
    setUser,
  } = useAuth();
  const { theme, setTheme } = useTheme();
  const { t } = useLanguage();
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "Error">(
    "success",
  );
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [tglinkUrl, setTglinkUrl] = useState<string | null>(null);
  const [tglinkState, setTglinkState] = useState<string | null>(null);
  const [tglinkLoading, setTglinkLoading] = useState(false);
  const [tglinkError, setTglinkError] = useState(false);
  const [tglinkWaiting, setTglinkWaiting] = useState(false);
  const linkPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );
  const linkPollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const languages = getAvailableLanguages().map((code) => ({
    code,
    name: getLanguageDisplayName(code),
  }));

  const stoplinkPolling = useCallback(() => {
    if (linkPollIntervalRef.current) {
      clearInterval(linkPollIntervalRef.current);
      linkPollIntervalRef.current = null;
    }
    if (linkPollTimeoutRef.current) {
      clearTimeout(linkPollTimeoutRef.current);
      linkPollTimeoutRef.current = null;
    }
    setTglinkWaiting(false);
  }, []);

  const startlinkPolling = useCallback(
    (state: string) => {
      stoplinkPolling();
      setTglinkWaiting(true);
      let elapsed = 0;
      linkPollIntervalRef.current = setInterval(async () => {
        try {
          const res = await pollTelegramAuth(state);
          if (res.status === "completed") {
            stoplinkPolling();

            router.refresh();
            await refreshUser();
            setMessage(t("texts.telegram_linked_success"));
            setMessageType("success");
            setTimeout(() => setMessage(""), 3000);
          }
        } catch {

        }
        elapsed += link_POLL_INTERVAL;
        if (elapsed >= link_POLL_TIMEOUT) {
          stoplinkPolling();
          setMessage(t("texts.login_timeout"));
          setMessageType("Error");
        }
      }, link_POLL_INTERVAL);

      linkPollTimeoutRef.current = setTimeout(() => {
        stoplinkPolling();
      }, link_POLL_TIMEOUT);
    },
    [stoplinkPolling, refreshUser, router, t],
  );

  useEffect(() => {
    return () => {
      stoplinkPolling();
    };
  }, [stoplinkPolling]);

  const fetchTglinkUrl = useCallback(async () => {
    if (!authUser || authUser.telegram_id > 0) return;
    setTglinkLoading(true);
    setTglinkError(false);
    try {
      const res = await startTelegramLink();
      setTglinkUrl(res.url);
      setTglinkState(res.state);
    } catch {
      setTglinkUrl(null);
      setTglinkState(null);
      setTglinkError(true);
    } finally {
      setTglinkLoading(false);
    }
  }, [authUser]);

  useEffect(() => {
    if (authLoading) return;
    if (!authUser) {
      router.replace("/login?next=/settings");
    }
  }, [authLoading, authUser, router]);

  useEffect(() => {
    if (authLoading || !authUser || authUser.telegram_id > 0) return;

    
    void fetchTglinkUrl();
  }, [authLoading, authUser, fetchTglinkUrl]);

  const handlelanguageChange = async (lang: string) => {
    if (!authUser) return;

    try {
      await changeLanguage(lang);
      setCurrentLang(lang);
      setUser((prev) => (prev ? { ...prev, language: lang } : prev));
      setMessage(
        t("texts.language_changed", { name: getLanguageDisplayName(lang) }),
      );
      setMessageType("success");
      setTimeout(() => setMessage(""), 3000);
    } catch (err) {
      setMessage(
        String(err)
      );
      setMessageType("Error");
    }
  };

  const handleChangePassword = async () => {
    if (!authUser) return;
    if (newPassword.length < 10) {
      setMessage(t("texts.password_too_short"));
      setMessageType("Error");
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setMessage(t("texts.passwords_mismatch"));
      setMessageType("Error");
      return;
    }

    try {
      await changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      });
      setMessage(t("texts.password_changed_success"));
      setMessageType("success");
      setTimeout(() => setMessage(""), 3000);
      setOldPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
    } catch (err) {
      setMessage(
        String(err)
      );
      setMessageType("Error");
    }
  };

  if (authLoading || !authUser) {
    return (
      <>
        <Header currentPage="/settings" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t("texts.loading")}</h1>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Header currentPage="/settings" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.settings_title")}</h1>
              <p className="profile-username">{t("texts.settings_subtitle")}</p>
            </div>
          </div>

          {message && (
            <div
              className={
                messageType === "success" ? "success-message" : "error-message"
              }
            >
              {message}
            </div>
          )}

          <div className="pinned-section fade-in">
            <h2>{t("texts.language")}</h2>
            <div className="pinned-content">
              <div
                className="flex-center mt-4"
                style={{ flexDirection: "column", gap: "8px" }}
              >
                {languages.map((lang) => {
                  const isActive = authUser?.language === lang.code;
                  return (
                    <button
                      key={lang.code}
                      type="button"
                      onClick={() => handlelanguageChange(lang.code)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "12px",
                        padding: "12px 16px",
                        width: "100%",
                        cursor: "pointer",
                        border: isActive
                          ? "1px solid var(--accent)"
                          : "1px solid var(--border-color)",
                        background: isActive
                          ? "var(--accent-glow)"
                          : "var(--bg-tertiary)",
                        color: "var(--text-primary)",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "14px",
                        textAlign: "left",
                        transition: "all var(--transition)",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: "20px",
                          height: "20px",
                          borderRadius: "50%",
                          border: isActive
                            ? "2px solid var(--accent)"
                            : "2px solid var(--border-color)",
                          background: isActive
                            ? "var(--accent)"
                            : "transparent",
                          flexShrink: 0,
                        }}
                      >
                        {isActive && (
                          <svg
                            width="12"
                            height="12"
                            viewBox="0 0 12 12"
                            fill="none"
                            style={{ color: "#fff" }}
                          >
                            <path
                              d="M2 6l3 3 5-5"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </span>
                      <span>{lang.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-1">
            <h2>{t("texts.theme")}</h2>
            <div className="pinned-content">
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  marginTop: "16px",
                }}
              >
                <button
                  onClick={() => setTheme("dark")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    padding: "12px 16px",
                    background:
                      theme === "dark" ? "var(--accent-glow)" : "transparent",
                    borderRadius: "var(--radius-sm)",
                    cursor: "pointer",
                    border:
                      theme === "dark"
                        ? "1px solid var(--accent)"
                        : "1px solid transparent",
                    color: "var(--text-primary)",
                    fontSize: "14px",
                    width: "100%",
                    textAlign: "left",
                  }}
                >
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }}
                  >
                    <MoonIcon /> {t("buttons.dark_theme")}
                  </span>
                </button>
                <button
                  onClick={() => setTheme("light")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    padding: "12px 16px",
                    background:
                      theme === "light" ? "var(--accent-glow)" : "transparent",
                    borderRadius: "var(--radius-sm)",
                    cursor: "pointer",
                    border:
                      theme === "light"
                        ? "1px solid var(--accent)"
                        : "1px solid transparent",
                    color: "var(--text-primary)",
                    fontSize: "14px",
                    width: "100%",
                    textAlign: "left",
                  }}
                >
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }}
                  >
                    <SunIcon /> {t("buttons.light_theme")}
                  </span>
                </button>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-2">
            <h2>{t("buttons.change_password")}</h2>
            <div className="pinned-content">
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  marginTop: "16px",
                }}
              >
                <input
                  type="password"
                  placeholder={t("texts.old_password")}
                  className="faq-search-input"
                  style={{ marginBottom: "0" }}
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                />
                <input
                  type="password"
                  placeholder={t("texts.new_password")}
                  className="faq-search-input"
                  style={{ marginBottom: "0" }}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <input
                  type="password"
                  placeholder={t("texts.confirm_new_password")}
                  className="faq-search-input"
                  style={{ marginBottom: "0" }}
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                />
                <button
                  onClick={handleChangePassword}
                  className="button"
                  style={{ width: "100%" }}
                >
                  {t("buttons.change_password")}
                </button>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-2">
            <h2>{t("buttons.link_telegram")}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: "16px" }}>
                <p
                  style={{
                    color: "var(--text-secondary)",
                    marginBottom: "16px",
                  }}
                >
                  {authUser && authUser.telegram_id > 0
                    ? t("texts.telegram_linked_permanent", {
                        id: authUser.telegram_id,
                      })
                    : t("texts.telegram_unlinked")}
                </p>
                {authUser && authUser.telegram_id > 0 ? (
                  <div
                    style={{
                      padding: "12px",
                      background: "var(--bg-tertiary)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "14px",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {t("texts.telegram_linked_note")}
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px",
                    }}
                  >
                    {tglinkLoading ? (
                      <div
                        style={{
                          padding: "12px",
                          background: "var(--bg-tertiary)",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "14px",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {t("texts.loading")}
                      </div>
                    ) : tglinkError ? (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "8px",
                        }}
                      >
                        <div
                          style={{
                            padding: "12px",
                            background: "var(--bg-tertiary)",
                            borderRadius: "var(--radius-sm)",
                            fontSize: "14px",
                            color: "var(--danger)",
                          }}
                        >
                          {t("texts.telegram_link_failed")}
                        </div>
                        <button
                          onClick={fetchTglinkUrl}
                          className="button"
                          style={{ width: "100%" }}
                        >
                          {t("buttons.retry")}
                        </button>
                      </div>
                    ) : tglinkUrl ? (
                      <a
                        href={tglinkUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="button"
                        style={{
                          width: "100%",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: "8px",
                          background: "var(--accent)",
                          color: "#fff",
                        }}
                        onClick={() => {
                          if (tglinkState) {
                            startlinkPolling(tglinkState);
                          }
                        }}
                      >
                        <svg
                          width="20"
                          height="20"
                          viewBox="0 0 24 24"
                          fill="currentColor"
                        >
                          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 0 0-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z" />
                        </svg>
                        {t("buttons.link_telegram")}
                      </a>
                    ) : (
                      <div
                        style={{
                          padding: "12px",
                          background: "var(--bg-tertiary)",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "14px",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {t("texts.loading")}
                      </div>
                    )}
                    <p
                      style={{
                        fontSize: "13px",
                        color: "var(--text-secondary)",
                        textAlign: "center",
                      }}
                    >
                      {t("texts.telegram_link_hint")}
                    </p>
                    {tglinkWaiting && (
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
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-3">
            <h2>{t("texts.account")}</h2>
            <div className="pinned-content">
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px",
                  marginTop: "16px",
                }}
              >
                <div
                  style={{
                    padding: "12px",
                    background: "var(--bg-tertiary)",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "14px",
                  }}
                >
                  <div style={{ marginBottom: "8px" }}>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {t("texts.web_login")}:{" "}
                    </span>
                    <span>{authUser?.login || authUser?.username || "-"}</span>
                  </div>
                  {authUser &&
                    Number(authUser.telegram_id) > 0 &&
                    authUser?.username && (
                      <div style={{ marginBottom: "8px" }}>
                        <span style={{ color: "var(--text-secondary)" }}>
                          {t("texts.telegram_username_label")}:{" "}
                        </span>
                        <span>@{authUser.username}</span>
                      </div>
                    )}
                  <div style={{ marginBottom: "8px" }}>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {t("texts.user_id")}:{" "}
                    </span>
                    <span>{authUser?.user_id}</span>
                  </div>
                  <div style={{ marginBottom: "8px" }}>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {t("texts.telegram_id_label")}:{" "}
                    </span>
                    <span>{authUser?.telegram_id || "-"}</span>
                  </div>
                  <div style={{ marginBottom: "8px" }}>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {t("texts.trust_score")}:{" "}
                    </span>
                    <span>{authUser?.trust_score}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-secondary)" }}>
                      {t("texts.discount")}:{" "}
                    </span>
                    <span>{authUser?.discount_percent}%</span>
                  </div>
                </div>
                <button
                  onClick={async () => {
                    await logout();
                  }}
                  className="button"
                  style={{ width: "100%", background: "var(--danger)" }}
                >
                  {t("buttons.logout")}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}




























