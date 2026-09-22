import type { NextConfig } from "next";

const botApiOrigin = (() => {
  try {
    return new URL(
      process.env.BOT_API_URL ||
        process.env.NEXT_PUBLIC_BOT_API_URL ||
        "http://localhost:2005/api/v1",
    ).origin;
  } catch {
    return "http://localhost:2005";
  }
})();
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "X-XSS-Protection",
            value: "0",
          },
          {
            key: "Referrer-Policy",
            value: "origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ${botApiOrigin}; frame-ancestors 'none'; base-uri 'self'`,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
