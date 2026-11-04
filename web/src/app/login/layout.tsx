import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { resolveLanguage } from "@/lib/i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolveLanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );

  const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN Service";
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";

  return {
    title: "Вход в аккаунт - " + siteName,
    description: "Войдите в свой аккаунт " + siteName + ". Быстрый вход через логин/пароль или через Telegram. Безопасный доступ к вашему VPN профилю.",
    keywords: ["vpn вход", "вход в аккаунт vpn", "vpn логин", "телеграм вход vpn"],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      siteName,
      title: "Вход в аккаунт - " + siteName,
      description: "Вход в личный кабинет " + siteName + ". Быстрая авторизация через логин/пароль или Telegram.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Вход - " + siteName,
      description: "Авторизация в " + siteName,
      images: ["/icon.jpg"],
    },
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
