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
    title: "Публичная оферта - " + siteName,
    description: "Публичная оферта " + siteName + ". Полный текст оферты на оказание VPN-услуг. Условия, оплата, сроки, ответственность, возвраты.",
    keywords: [
      "публичная оферта vpn",
      "оферта vpn",
      "договор оферты vpn",
      "условия оферты vpn",
      "оферта vpn service",
    ],
    openGraph: {
      type: "website",
      locale: lang + "_" + lang.toUpperCase(),
      url: siteUrl,
      title: "Публичная оферта - " + siteName,
      description: "Полный текст публичной оферты " + siteName + ". Условия оказания услуг, оплата, ответственность.",
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: "Публичная оферта - " + siteName,
      description: "Полный текст публичной оферты " + siteName,
      images: ["/icon.jpg"],
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function OfferLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
