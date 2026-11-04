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
    title: "Партнёрская программа - " + siteName,
    description: "Станьте партнёром " + siteName + ". Гибкие бонусы за приглашённых, доход от комиссий, личный кабинет партнёра. Условия: от 1000 подписчиков.",
    keywords: [
      "партнёрская программа vpn",
      "партнёрка vpn",
      "партнёрство vpn",
      "пригласить друга vpn",
      "заработок на vpn",
      "реферальная программа vpn",
      "партнёрский кабинет vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Партнёрская программа - " + siteName,
      description: "Станьте партнёром " + siteName + ". Гибкая система бонусов, прозрачная статистика, ежемесячные выплаты.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Партнёрство - " + siteName,
      description: "Партнёрская программа " + siteName + " с гибкими бонусами",
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function PartnerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
