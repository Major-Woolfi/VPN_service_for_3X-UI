"use client";

import { useEffect } from "react";
import Header from "@/components/Header";
import { useLanguage } from "@/contexts/LanguageContext";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useLanguage();

  useEffect(() => {
    console.error("Application error", error);
  }, [error]);

  return (
    <>
      <Header currentPage="" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.error")}</h1>
            </div>
          </div>
          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <p style={{ color: "var(--text-secondary)", marginBottom: "16px" }}>
                {t("texts.unexpected_error")}
              </p>
              <button type="button" onClick={reset} className="button">
                {t("buttons.continue")}
              </button>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
