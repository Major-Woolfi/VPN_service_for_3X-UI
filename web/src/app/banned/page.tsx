"use client";

import Header from "@/components/Header";
import { useLanguage } from "@/contexts/LanguageContext";
import { useFeatures } from "@/contexts/FeaturesContext";
import { getPublicLinksFromFeatures } from "@/lib/api";

export default function BannedPage() {
  const { t } = useLanguage();
  const { features } = useFeatures();
  const publicLinks = getPublicLinksFromFeatures(features);

  const supportHref = publicLinks.support_url || null;

  return (
    <>
      <Header currentPage="/banned" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">
                {t("texts.account_banned_title")}
              </h1>
            </div>
          </div>
          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <p style={{ marginTop: "16px", color: "var(--text-secondary)" }}>
                {t("texts.account_banned_message")}
              </p>
              <div style={{ marginTop: "24px", textAlign: "center" }}>
                {supportHref ? (
                  <a
                    href={supportHref}
                    className="button"
                    style={{ textDecoration: "none" }}
                  >
                    {t("buttons.contact_support")}
                  </a>
                ) : (
                  <span style={{ color: "var(--text-secondary)" }}>
                    {t("texts.support_not_configured")}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
