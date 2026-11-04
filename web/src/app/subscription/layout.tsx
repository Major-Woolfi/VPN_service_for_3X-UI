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
    title: "Моя подписка - " + siteName,
    description: "Управление VPN подпиской. Просмотр статуса, трафика, срока действия, продление, смена тарифа, отмена автопродления.",
    keywords: [
      "моя подписка vpn",
      "подписка vpn",
      "статус подписки vpn",
      "продлить подписку vpn",
      "продлить vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Моя подписка - " + siteName,
      description: "Управление VPN подпиской: статус, трафик, срок действия, продление, смена тарифа.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Моя подписка - " + siteName,
      description: "Управление VPN подпиской",
      images: ["/icon.jpg"],
    },
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function SubscriptionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
