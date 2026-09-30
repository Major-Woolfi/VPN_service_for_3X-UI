import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BackToTop from "@/components/BackToTop";
import ThemeInit from "@/components/ThemeInit";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { FeaturesProvider } from "@/contexts/FeaturesContext";
import { getFeaturesServer } from "@/lib/server/bot-data";
import ScrollAnimations from "@/components/ScrollAnimations";
import AuthCallback from "@/components/AuthCallback";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { generateJsonLdScript } from "@/lib/structured-data";
import {
  getServerLanguages,
  getServerSiteCopy,
  normalizeServerLanguage,
} from "@/lib/i18n-server";
import { resolveServerSession } from "@/lib/server/session";

const inter = Inter({
  subsets: ["cyrillic", "latin"],
  variable: "--font-inter",
});

const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "vpn";

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = normalizeServerLanguage(
    cookieStore.get("vpn_language")?.value ||
      headerStore.get("accept-language") ||
      undefined,
  );
  const copy = getServerSiteCopy(lang);
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";
  const languageAlternates = Object.fromEntries(
    getServerLanguages().map((language) => [
      language,
      `${siteUrl}/${language}`,
    ]),
  );

  return {
    metadataBase: new URL(siteUrl),
    title: {
      default: siteName,
      template: `%s | ${siteName}`,
    },
    description: copy.siteDescription,
    keywords: [
      "vpn",
      "xray",
      "vless",
      "vmess",
      "trojan",
      "shadowsocks",
      "hysteria",
      "reality",
    ],
    authors: [{ name: siteName }],
    creator: siteName,
    openGraph: {
      type: "website",
      locale: lang,
      url: process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local",
      siteName,
      title: `${siteName} - ${copy.siteTitle}`,
      description: copy.twitterDescription,
      images: [
        {
          url: "/icon.jpg",
          width: 512,
          height: 512,
          alt: siteName,
        },
      ],
    },
    alternates: {
      languages: languageAlternates,
    },
    twitter: {
      card: "summary",
      title: siteName,
      description: copy.twitterDescription,
      images: ["/icon.jpg"],
    },
    icons: {
      icon: [{ url: "/icon.jpg", type: "image/jpeg" }],
      apple: "/icon.jpg",
    },
    manifest: "/manifest.json",
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = normalizeServerLanguage(
    cookieStore.get("vpn_language")?.value ||
      headerStore.get("accept-language") ||
      undefined,
  );

  // Профиль подтягивается на сервере: страница рендерится сразу
  // с данными, без "загрузка..." и без лишнего клиентского запроса.
  // Если cookie есть, но сессия на боте уже недействительна -
  // редиректим сразу, не дожидаясь первого клиентского запроса.
  const pathname = headerStore.get("x-pathname") || "";
  const isGuestPage =
    pathname === "/login" ||
    pathname === "/register" ||
    pathname.startsWith("/login/") ||
    pathname.startsWith("/register/");

  const session = await resolveServerSession();
  if (session.kind === "expired" && !isGuestPage) {
    // Route Handler чистит cookie и уводит на /login (Server Component
    // не может удалять cookie). На гостевых страницах редирект не делаем,
    // иначе возникает петля.
    redirect("/api/session/expired");
  }
  // Забаненного не разлогиниваем - он должен увидеть причину бана.
  if (session.kind === "banned" && !isGuestPage) {
    redirect("/banned");
  }
  const initialUser = session.kind === "authenticated" ? session.user : null;
  // Один серверный запрос /config/features на рендер вместо дубля
  // (серверный + клиентский FeaturesProvider) на каждой странице.
  const initialFeatures = await getFeaturesServer();

  return (
    <html
      lang={lang}
      className={`${inter.variable} h-full antialiased theme-dark`}
      suppressHydrationWarning
    >
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <meta name="robots" content="index, follow" />
        <meta name="theme-color" content="#0a0a0a" />
        <link
          rel="canonical"
          href={process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={generateJsonLdScript(lang)}
        />
      </head>
      <body className="min-h-full flex flex-col font-sans">
        <ThemeInit />
        <ThemeProvider>
          <AuthProvider initialUser={initialUser}>
            <LanguageProvider initialLang={lang}>
              <FeaturesProvider initialFeatures={initialFeatures}>
                <AuthCallback />
                {children}
                <BackToTop />
                <ScrollAnimations />
              </FeaturesProvider>
            </LanguageProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
