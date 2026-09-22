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

  if (authLoading || !user) return null;

  return (
    <>
      <Header currentPage="/subscription" />
      <main>
        <div className="profile">
          <div className="pinned-section">
            <p>{t("texts.loading")}</p>
          </div>
        </div>
      </main>
    </>
  );
}
