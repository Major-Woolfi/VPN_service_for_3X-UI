import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { resolveLanguage } from "@/lib/i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN Service";
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";
  const lang = resolveLanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );

  return {
    title: "Мой профиль - " + siteName,
    description: "Личный кабинет " + siteName + ". Управление подпиской, просмотр статистики трафика, настройка клиентов, реферальная программа, история платежей.",
    keywords: [
      "профиль vpn",
      "личный кабинет vpn",
      "управление подпиской vpn",
      "статистика трафика vpn",
      "настройки vpn",
    ],
    openGraph: {
      type: "profile",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Профиль - " + siteName,
      description: "Личный кабинет " + siteName + ". Управление подпиской, трафик, настройки, рефералы.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Профиль - " + siteName,
      description: "Личный кабинет " + siteName,
      images: ["/icon.jpg"],
    },
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function ProfileLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
