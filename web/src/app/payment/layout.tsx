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
    title: "Выбор тарифа и оплата - " + siteName,
    description: "Оформите подписку на " + siteName + ". Гибкие тарифы: кастомные и готовые. Оплата через ЮMoney или P2P. Мгновенная активация после подтверждения.",
    keywords: [
      "оплата vpn",
      "купить vpn",
      "подписка vpn",
      "тарифы vpn",
      "оплата vpn картой",
      "продлить vpn",
      "продлить подписку vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Оплата подписки - " + siteName,
      description: "Оплата и продление VPN подписки. ЮMoney, P2P перевод. Мгновенная активация после подтверждения платежа.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Оплата VPN - " + siteName,
      description: "Оплата и продление VPN подписки",
      images: ["/icon.jpg"],
    },
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function PaymentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
