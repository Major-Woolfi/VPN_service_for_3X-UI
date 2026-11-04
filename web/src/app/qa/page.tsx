import { cookies, headers } from "next/headers";
import Header from "@/components/Header";
import FaqList from "@/components/FaqList";
import { tServer, resolveLanguage } from "@/lib/i18n-server";

export async function generateMetadata() {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolveLanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );
  const t = (key: string, params?: Record<string, string | number>) =>
    tServer(lang, key, params);

  const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN Service";
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";

  return {
    title: `${t("texts.qa")} - ${siteName}`,
    description: t("texts.qa_subtitle"),
    keywords: [
      "faq vpn",
      "вопросы про vpn",
      "настройка vpn",
      "vpn не работает",
      "vpn тарифы",
      "реферальная программа vpn",
      "партнёрская программа vpn",
      "оплата vpn",
      "пробный период vpn",
      "vpn настройка",
    ],
    alternates: {
      canonical: `${siteUrl}/qa`,
    },
    openGraph: {
      type: "website",
      locale: lang,
      url: `${siteUrl}/qa`,
      siteName,
      title: `${t("texts.qa")} - ${siteName}`,
      description: t("texts.qa_subtitle"),
      images: [
        {
          url: "/icon.jpg",
          width: 512,
          height: 512,
          alt: `${siteName} FAQ`,
        },
      ],
    },
    twitter: {
      card: "summary",
      title: `${t("texts.qa")} - ${siteName}`,
      description: t("texts.qa_subtitle"),
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function QaPage() {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolveLanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );
  const t = (key: string, params?: Record<string, string | number>) =>
    tServer(lang, key, params);

  return (
    <>
      <Header currentPage="/qa" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.qa")}</h1>
              <p className="profile-username">{t("texts.qa_subtitle")}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t("texts.qa_faq_title")}</h2>
            <div className="pinned-content">
              <FaqList />
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
