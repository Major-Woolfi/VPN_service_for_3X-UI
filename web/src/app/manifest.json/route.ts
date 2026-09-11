import { NextResponse } from 'next/server';

export async function GET() {
  const siteName = process.env.NEXT_PUBLIC_VPN_NAME || 'VPN';
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://vpn.local';

  const manifest = {
    name: siteName,
    short_name: siteName,
    description: `Быстрый и надёжный VPN-сервис ${siteName} на базе XRay`,
    start_url: '/',
    display: 'standalone',
    background_color: '#0d1117',
    theme_color: '#0d1117',
    icons: [
      {
        src: '/icon.jpg',
        sizes: '512x512',
        type: 'image/jpeg',
        purpose: 'any maskable',
      },
    ],
  };

  return NextResponse.json(manifest, {
    headers: {
      'Content-Type': 'application/manifest+json',
    },
  });
}
