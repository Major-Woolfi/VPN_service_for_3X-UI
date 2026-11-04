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
    title: "Условия использования - " + siteName,
    description: "Условия использования " + siteName + ". Правила пользования сервисом, права и обязанности сторон, ответственность, оплата и возврат средств.",
    keywords: [
      "условия использования vpn",
      "условия сервиса vpn",
      "пользовательское соглашение vpn",
      "правила vpn",
      "tos vpn",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Условия использования - " + siteName,
      description: "Официальные условия использования " + siteName + ". Полный текст пользовательского соглашения.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Условия использования - " + siteName,
      description: "Полный текст условий использования " + siteName,
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function TosLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
