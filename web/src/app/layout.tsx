import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BackToTop from "@/components/BackToTop";
import ThemeInit from "@/components/ThemeInit";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { FeaturesProvider } from "@/contexts/FeaturesContext";
import { getFeaturesServer, getTariffsServer } from "@/lib/server/bot-data";
import ScrollAnimations from "@/components/ScrollAnimations";
import AuthCallback from "@/components/AuthCallback";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { generateJsonLdScript } from "@/lib/structured-data";
import { getServerSiteCopy, normalizeServerlanguage, type SiteCopy } from "@/lib/i18n-server";
import { resolveServerSession } from "@/lib/server/session";
import { getOpenGraphLocale } from "@/lib/locale";

const inter = Inter({
  subsets: ["cyrillic", "latin"],
  variable: "--font-inter",
});

const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "vpn";

const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("vpn_theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}var r=document.documentElement;r.classList.remove("theme-dark","theme-light");r.classList.add("theme-"+t);r.style.colorScheme=t;}catch(e){document.documentElement.classList.add("theme-dark");}})();`;

function getPageType(
  pathname: string,
):
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
  | "co-owners"
  | "tos"
  | "privacy"
  | "offer"
  | "banned"
  | "admin" {
  if (pathname === "/") return "home";
  if (pathname === "/banned" || pathname.startsWith("/banned/")) {
    return "banned";
  }
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return "admin";
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
  if (pathname === "/co-owners" || pathname.startsWith("/co-owners/")) return "co-owners";
  if (pathname === "/tos" || pathname.startsWith("/tos/")) return "tos";
  if (pathname === "/privacy" || pathname.startsWith("/privacy/")) {
    return "privacy";
  }
  if (pathname === "/offer" || pathname.startsWith("/offer/")) return "offer";
  return "home";
}

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = normalizeServerlanguage(
    cookieStore.get("vpn_language")?.value || headerStore.get("accept-language") || undefined,
  );
  const emptyLegal = () => ({
    title: "",
    subtitle: "",
    effectiveDate: "",
    sections: [],
  });
  let copy: SiteCopy;
  try {
    copy = getServerSiteCopy(lang);
  } catch {
    copy = {
      siteDescription: "",
      siteTitle: "",
      twitterDescription: "",
      legal: {
        tos: emptyLegal(),
        privacy: emptyLegal(),
        offer: emptyLegal(),
      },
    };
  }
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";
  const pathname = headerStore.get("x-pathname") || "";

  const dynamickeywords = [
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
    "POST-quantum",
    "POST-quantum cryptography",
    "ml-kem",
    "xray",
    "vless protocol",
    "reality protocol",
    "xhttp",
    "POST-quantum vpn",
    "vpn с POST-квантовой защитой",
    "vpn обход блокировок",
    "vpn белые списки",
    "vpn обход белых списков",
    "vpn no logs",
    "vpn no logs",
    "vpn ml-kem-768",
    "vpn ml-kem",
    "vpn kyber",
    "vpn POST-quantum",
    "приватность",
    "анонимность",
    "vpn для россии",
    "vpn для обхода блокировок",
    "vpn белые списки обход",
    "vpn xray",
    "vpn vless",
    "vpn shadowsocks",
    "vpn reality",
    "дешевый vpn",
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
    "POST-quantum vpn",
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
    keywords: [...new Set(dynamickeywords)],
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
      locale: getOpenGraphLocale(lang),
      url: `${siteUrl}${pathname}`,
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
      canonical: `${siteUrl}${pathname}`,
    },
    twitter: {
      card: "summary_large_image",
      title: siteName,
      description: copy.twitterDescription,
      images: ["/icon.jpg"],
      creator: siteName,
      site: siteName,
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

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = normalizeServerlanguage(
    cookieStore.get("vpn_language")?.value || headerStore.get("accept-language") || undefined,
  );

  const pathname = headerStore.get("x-pathname") || "";
  const isGuestPage =
    pathname === "/login" ||
    pathname === "/register" ||
    pathname.startsWith("/login/") ||
    pathname.startsWith("/register/");
  const isBannedPage = pathname === "/banned";

  const session = await resolveServerSession();
  if (session.kind === "expired" && !isGuestPage && !isBannedPage) {
    redirect("/api/session/expired");
  }

  if (session.kind === "banned" && !isGuestPage && !isBannedPage) {
    redirect("/banned");
  }
  const initialUser = session.kind === "authenticated" ? session.user : null;
  if (
    pathname.startsWith("/co-owners") &&
    session.kind === "authenticated" &&
    !session.user.is_coowner
  ) {
    redirect("/profile");
  }

  const [initialFeatures, tariffData] = await Promise.all([
    getFeaturesServer(),
    getTariffsServer(),
  ]);
  const tariffs = tariffData.tariffs;
  const catalogPrices = tariffs
    .filter((tariff) => tariff.active && !tariff.is_trial && tariff.id !== "custom")
    .map((tariff) => tariff.price_rub)
    .filter((price) => Number.isFinite(price) && price > 0);
  const priceRange =
    catalogPrices.length > 0
      ? {
          low: Math.min(...catalogPrices),
          high: Math.max(...catalogPrices),
          currency: "RUB",
        }
      : undefined;

  return (
    <html
      lang={lang}
      className={`${inter.variable} h-full antialiased theme-dark`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <meta name="theme-color" content="#0a0a0a" />
        <meta name="color-scheme" content="dark" />
        <link rel="preconnect" href={process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"} />
        <link rel="dns-prefetch" href={process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local"} />
        <link rel="preload" as="image" href="/icon.jpg" type="image/jpeg" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={generateJsonLdScript(
            lang,
            getPageType(pathname),
            pathname,
            priceRange,
          )}
        />
      </head>
      <body className="min-h-full flex flex-col font-sans">
        <ThemeInit />
        <ThemeProvider>
          <AuthProvider key={initialUser?.user_id ?? "anon"} initialUser={initialUser}>
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
