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
    title: "Реферальная программа - " + siteName,
    description: "Реферальная программа " + siteName + ". Приглашайте друзей и получайте бонусные дни подписки. Ваша реферальная ссылка, статистика приглашений, бонусы.",
    keywords: [
      "реферальная программа vpn",
      "реферальная ссылка vpn",
      "пригласить друга vpn",
      "бонус за друга vpn",
      "рефералка vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Реферальная программа - " + siteName,
      description: "Реферальная программа " + siteName + ". Приглашайте друзей, получайте бонусные дни. Ваша уникальная реферальная ссылка.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Реферальная программа - " + siteName,
      description: "Приглашайте друзей в " + siteName + " и получайте бонусы",
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function ReferralLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
