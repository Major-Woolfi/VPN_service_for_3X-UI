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
    title: "Настройки - " + siteName,
    description: "Настройки аккаунта " + siteName + ". Язык, тема, привязка Telegram, смена пароля, двухфакторная аутентификация, безопасность.",
    keywords: [
      "настройки vpn",
      "настройки аккаунта vpn",
      "смена пароля vpn",
      "привязка telegram vpn",
      "безопасность vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Настройки - " + siteName,
      description: "Настройки аккаунта " + siteName + ": язык, тема, Telegram, пароль, безопасность.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Настройки - " + siteName,
      description: "Настройки аккаунта и безопасности " + siteName,
      images: ["/icon.jpg"],
    },
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
