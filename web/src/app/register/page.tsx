"use client";

import Header from "@/components/Header";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { registerUser } from "@/lib/api";
import { useLanguage } from "@/contexts/LanguageContext";

function safeNextPath(): string {
  if (typeof window === "undefined") return "/settings";
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  // Без явного next ведём в настройки: без Telegram-аккаунта
  // покупка подписки и партнёрство недоступны.
  return "/settings";
}

export default function RegisterPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const refCode = useSearchParams()?.get("ref") || "";

  const handlePasswordRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const sanitizedUsername = username.replace(/[<>"'&]/g, "").trim();
    if (sanitizedUsername.length < 3) {
      setError(t("texts.username_too_short"));
      return;
    }
    if (password.length < 10) {
      setError(t("texts.password_too_short"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("texts.passwords_mismatch"));
      return;
    }

    setLoading(true);
    try {
      await registerUser({
        username: sanitizedUsername,
        password,
        ref_code: refCode || undefined,
      });
      // Сессионная cookie уже установлена прокси - обновляем
      // серверный layout и уходим на профиль без доп. запросов.
      router.refresh();
      router.replace(safeNextPath());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.register_error"));
      setLoading(false);
    }
  };

  return (
    <>
      <Header currentPage="/register" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.register_title")}</h1>
              <p className="profile-username">{t("texts.register_subtitle")}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div className="flex flex-col gap-4 mt-5">
                {error && <div className="error-message">{error}</div>}

                <form
                  onSubmit={handlePasswordRegister}
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
                    autoComplete="new-password"
                    required
                  />
                  <input
                    type="password"
                    placeholder={t("texts.confirm_password")}
                    className="faq-search-input"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    required
                  />
                  <button
                    type="submit"
                    className="button w-full"
                    disabled={loading}
                  >
                    {loading ? t("texts.waiting") : t("buttons.register")}
                  </button>
                </form>

                <p className="text-center text-secondary text-sm">
                  {t("texts.have_account")}{" "}
                  <Link href="/login" className="font-semibold">
                    {t("buttons.login")}
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
