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

function getPageType(pathname: string):
  | "home"
  | "qa"
  | "partner"
  | "client"
  | "login"
  | "register"
  | "profile"
  | "settings"
  | "payment"
  | "subscription"
  | "subscribe"
  | "referral"
  | "tos"
  | "privacy"
  | "offer" {
  if (pathname === "/") return "home";
  if (pathname === "/qa") return "qa";
  if (pathname === "/partner") return "partner";
  if (pathname === "/client") return "client";
  if (pathname === "/login") return "login";
  if (pathname === "/register") return "register";
  if (pathname === "/profile") return "profile";
  if (pathname === "/settings") return "settings";
  if (pathname === "/payment") return "payment";
  if (pathname === "/subscription") return "subscription";
  if (pathname === "/subscribe") return "subscribe";
  if (pathname === "/referral") return "referral";
  if (pathname.startsWith("/tos")) return "tos";
  if (pathname.startsWith("/privacy")) return "privacy";
  if (pathname.startsWith("/offer")) return "offer";
  return "home";
}

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

  const dynamicKeywords = [
    "vpn",
    "xray",
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "hysteria",
    "reality",
    "ml-kem",
    "ml-kem-768",
    "kyber",
    "post-quantum",
    "post-quantum cryptography",
    "ml-kem",
    "xray",
    "vless protocol",
    "reality protocol",
    "xhttp",
    "post-quantum vpn",
    "vpn с post-квантовой защитой",
    "vpn обход блокировок",
    "vpn белые списки",
    "vpn обход белых списков",
    "vpn no logs",
    "vpn no logs",
    "vpn ml-kem-768",
    "vpn ml-kem",
    "vpn kyber",
    "vpn post-quantum",
    "приватность",
    "анонимность",
    "vpn для россии",
    "vpn для обхода блокировок",
    "vpn белые списки обход",
    "vpn xray",
    "vpn vless",
    "vpn shadowsocks",
    "vpn reality",
    "deшевый vpn",
    "cheap vpn",
    "бесплатный vpn",
    "free vpn",
    "vpn trial",
    "vpn trial period",
    "vpn switzerland",
    "swiss vpn",
    "vpn swiss",
    "no logs vpn",
    "vpn no logs",
    "vpn без логов",
    "vpn without logs",
    "vpn with kill switch",
    "vpn kill switch",
    "vpn split tunneling",
    "split tunneling vpn",
    "vpn for streaming",
    "vpn for netflix",
    "vpn for torrent",
    "vpn p2p",
    "vpn torrenting",
    "wireguard alternative",
    "openvpn alternative",
    "vless vpn",
    "shadowsocks vpn",
    "reality vpn",
    "xhttp vpn",
    "ml-kem-768 vpn",
    "kyber-768 vpn",
    "post-quantum vpn",
    "quantum resistant vpn",
    "vpn quantum resistant",
    "privacy vpn",
    "anonymous vpn",
    "secure vpn",
    "fast vpn",
    "high speed vpn",
    "unlimited vpn",
    "unlimited bandwidth vpn",
  ];

  return {
    metadataBase: new URL(siteUrl),
    title: {
      default: siteName,
      template: `%s | ${siteName}`,
    },
    description: copy.siteDescription,
    keywords: dynamicKeywords,
    authors: [{ name: siteName }],
    creator: siteName,
    publisher: siteName,
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-video-preview": -1,
        "max-image-preview": "large",
        "max-snippet": -1,
      },
    },
    openGraph: {
      type: "website",
      locale: lang,
      url: siteUrl,
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
      languages: {
        ...Object.fromEntries(
          getServerLanguages().map((language) => [
            language,
            `${siteUrl}/${language}`,
          ]),
        ),
        "x-default": siteUrl,
      },
    },
    twitter: {
      card: "summary_large_image",
      title: siteName,
      description: copy.twitterDescription,
      images: ["/icon.jpg"],
      creator: "@phantomvpn_off",
      site: "@phantomvpn_off",
    },
    icons: {
      icon: [{ url: "/icon.jpg", type: "image/jpeg" }],
      apple: "/icon.jpg",
      shortcut: "/icon.jpg",
    },
    manifest: "/manifest.json",
    verification: {
      google: process.env.GOOGLE_SITE_VERIFICATION,
      yandex: process.env.YANDEX_SITE_VERIFICATION,
    },
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

  const pathname = headerStore.get("x-pathname") || "";
  const isGuestPage =
    pathname === "/login" ||
    pathname === "/register" ||
    pathname.startsWith("/login/") ||
    pathname.startsWith("/register/");

  const session = await resolveServerSession();
  if (session.kind === "expired" && !isGuestPage) {

    redirect("/api/session/expired");
  }

  if (session.kind === "banned" && !isGuestPage) {
    redirect("/banned");
  }
  const initialUser = session.kind === "authenticated" ? session.user : null;

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
        <meta name="color-scheme" content="dark" />
        <link
          rel="canonical"
          href={`${process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"}${pathname}`}
        />
        {getServerLanguages().map((language) => (
          <link
            key={language}
            rel="alternate"
            hrefLang={language}
            href={`${process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"}/${language}${pathname}`}
          />
        ))}
        <link
          rel="alternate"
          hrefLang="x-default"
          href={`${process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"}${pathname}`}
        />
        <link rel="preconnect" href={process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"} />
        <link rel="dns-prefetch" href={process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"} />
        <link rel="preload" as="image" href="/icon.jpg" type="image/jpeg" />
        <link rel="preload" as="font" href="/fonts/inter-var-latin.woff2" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" as="font" href="/fonts/inter-var-cyrillic.woff2" type="font/woff2" crossOrigin="anonymous" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={generateJsonLdScript(lang, getPageType(pathname), pathname)}
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
