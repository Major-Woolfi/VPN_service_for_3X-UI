import { NextResponse } from "next/server";
import { cookies, headers } from "next/headers";
import { getServerSiteCopy, resolveLanguage } from "@/lib/i18n-server";

export async function GET() {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolveLanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );
  const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN";
  const copy = getServerSiteCopy(lang);
  const manifest = {
    name: siteName,
    short_name: siteName,
    description: copy.siteDescription,
    start_url: "/",
    display: "standalone",
    background_color: "#0d1117",
    theme_color: "#0d1117",
    icons: [
      {
        src: "/icon.jpg",
        sizes: "512x512",
        type: "image/jpeg",
        purpose: "any maskable",
      },
    ],
  };

  return NextResponse.json(manifest, {
    headers: {
      "Content-Type": "application/manifest+json",
    },
  });
}
