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
    title: "Политика конфиденциальности - " + siteName,
    description: "Политика конфиденциальности " + siteName + ". Какие данные собираются, как они используются, защита данных, no-logs политика, права пользователей.",
    keywords: [
      "политика конфиденциальности vpn",
      "privacy policy vpn",
      "защита данных vpn",
      "no logs vpn",
      "конфиденциальность vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Политика конфиденциальности - " + siteName,
      description: "Политика конфиденциальности " + siteName + ". No-Logs политика, защита данных, права пользователей.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Политика конфиденциальности - " + siteName,
      description: "Политика конфиденциальности " + siteName + ". No-Logs, защита данных.",
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function PrivacyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
