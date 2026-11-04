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
    title: "Регистрация - " + siteName,
    description: "Создайте аккаунт в " + siteName + ". Быстрая регистрация по email или через Telegram. Доступ к VPN, реферальная программа, партнёрская программа.",
    keywords: ["регистрация vpn", "создать аккаунт vpn", "зарегистрироваться в vpn", "vpn регистрация"],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      siteName,
      title: "Регистрация - " + siteName,
      description: "Создайте аккаунт в " + siteName + " за минуту. Доступ к VPN, реферальная программа, партнёрство.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Регистрация - " + siteName,
      description: "Регистрация нового аккаунта в " + siteName,
      images: ["/icon.jpg"],
    },
    robots: {
      index: false,
      follow: false,
    },
  };
}

export default async function RegisterLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
