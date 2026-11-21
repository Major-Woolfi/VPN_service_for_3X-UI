import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { getServerPageSeo, resolvelanguage } from "@/lib/i18n-server";
import { getOpenGraphLocale } from "@/lib/locale";

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolvelanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );
  const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN Service";
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";
  const seo = getServerPageSeo(lang, "partner");

  return {
    title: `${seo.title} - ${siteName}`,
    description: seo.description,
    openGraph: {
      type: "website",
      locale: getOpenGraphLocale(lang),
      url: `${siteUrl}/partner`,
      siteName,
      title: seo.title,
      description: seo.description,
      images: ["/icon.jpg"],
    },
    twitter: {
      card: "summary",
      title: seo.title,
      description: seo.description,
      images: ["/icon.jpg"],
      creator: siteName,
      site: siteName,
    },
    robots: {
      index: true,
      follow: true,
    },
  };
}

export default async function PartnerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
