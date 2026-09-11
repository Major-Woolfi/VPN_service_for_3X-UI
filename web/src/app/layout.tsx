import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import BackToTop from '@/components/BackToTop';
import ThemeInit from '@/components/ThemeInit';
import { AuthProvider } from '@/contexts/AuthContext';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { FeaturesProvider } from '@/contexts/FeaturesContext';
import ScrollAnimations from '@/components/ScrollAnimations';
import AuthCallback from '@/components/AuthCallback';
import { cookies, headers } from 'next/headers';
import { getSiteCopy, normalizeSiteLanguage } from '@/data/legal';
import { generateJsonLdScript } from '@/lib/structured-data';

const inter = Inter({
  subsets: ['cyrillic', 'latin'],
  variable: '--font-inter',
});

const siteName = process.env.NEXT_PUBLIC_VPN_NAME || 'vpn';

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = normalizeSiteLanguage(
    cookieStore.get('vpn_language')?.value || headerStore.get('accept-language') || undefined,
  );
  const copy = getSiteCopy(lang);

  return {
    metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'),
    title: {
      default: siteName,
      template: `%s | ${siteName}`,
    },
    description: copy.siteDescription,
    keywords: [
      'vpn',
      'xray',
      'vless',
      'vmess',
      'trojan',
      'shadowsocks',
      'hysteria',
      'reality',
    ],
    authors: [{ name: siteName }],
    creator: siteName,
    openGraph: {
      type: 'website',
      locale: lang,
      url: process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local',
      siteName,
      title: `${siteName} - ${copy.siteTitle}`,
      description: copy.twitterDescription,
      images: [
        {
          url: '/icon.jpg',
          width: 512,
          height: 512,
          alt: siteName,
        },
      ],
    },
    alternates: {
      languages: {
        ru: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/ru`,
        en: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/en`,
        pl: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/pl`,
        zh: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/zh`,
        be: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/be`,
        de: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/de`,
        ja: `${process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'}/ja`,
      },
    },
    twitter: {
      card: 'summary',
      title: siteName,
      description: copy.twitterDescription,
      images: ['/icon.jpg'],
    },
    icons: {
      icon: [{ url: '/icon.jpg', type: 'image/jpeg' }],
      apple: '/icon.jpg',
    },
    manifest: '/manifest.json',
  };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = normalizeSiteLanguage(
    cookieStore.get('vpn_language')?.value || headerStore.get('accept-language') || undefined,
  );

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
        <link rel="canonical" href={process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local'} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={generateJsonLdScript()}
        />
      </head>
      <body className="min-h-full flex flex-col font-sans">
        <ThemeInit />
        <ThemeProvider>
          <AuthProvider>
            <LanguageProvider>
              <FeaturesProvider>
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

