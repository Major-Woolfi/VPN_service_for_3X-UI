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
    title: "Настройка клиентов - " + siteName,
    description: "Скачайте VPN-клиенты для любой платформы: Windows, macOS, Linux, iOS, Android, роутеры. Гайды по настройке INCY, v2RayTun, NekoBox, Shadowrocket.",
    keywords: [
      "vpn клиенты",
      "скачать vpn клиент",
      "настройка vpn клиента",
      "incy vpn",
      "v2rayn vpn",
      "nekoBox vpn",
      "shadowrocket vpn",
      "vpn на роутере",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Настройка клиентов - " + siteName,
      description: "Скачайте VPN-клиенты для Windows, macOS, Linux, iOS, Android, роутеры. Подробные гайды по настройке.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Клиенты VPN - " + siteName,
      description: "VPN-клиенты для всех платформ",
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function ClientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
