"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import Header from "@/components/Header";
import { useLanguage } from "@/contexts/LanguageContext";

export default function SubscriptionRedirectPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { t } = useLanguage();

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/subscribe");
      return;
    }
    router.replace("/subscribe");
  }, [authLoading, user, router]);

  return (
    <>
      <Header currentPage="/subscription" />
      <main>
        <div className="profile">
          <div className="pinned-section">
            <div className="waiting-indicator" role="status">
              <span className="spinner" aria-hidden="true" />
              {t("texts.loading")}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
