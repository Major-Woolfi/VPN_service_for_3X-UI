import { getServerSiteCopy, normalizeServerLanguage } from "./i18n-server";

const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN";
const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "";

export function generateJsonLd(language?: string) {
  const normalizedLanguage = normalizeServerLanguage(language);
  const copy = getServerSiteCopy(normalizedLanguage);
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${baseUrl}/#organization`,
        name: siteName,
        url: baseUrl,
        logo: `${baseUrl}/icon.jpg`,
        foundingDate: "2026-07-07",
      },
      {
        "@type": "WebSite",
        "@id": `${baseUrl}/#website`,
        url: baseUrl,
        name: siteName,
        description: copy.siteDescription,
        publisher: {
          "@id": `${baseUrl}/#organization`,
        },
        inLanguage: [normalizedLanguage],
      },
      {
        "@type": "WebPage",
        "@id": `${baseUrl}/#webpage`,
        url: baseUrl,
        name: `${siteName} - ${copy.siteTitle}`,
        isPartOf: {
          "@id": `${baseUrl}/#website`,
        },
        about: {
          "@id": `${baseUrl}/#organization`,
        },
      },
    ],
  };
}

export function generateJsonLdScript(language?: string) {
  return { __html: JSON.stringify(generateJsonLd(language)) };
}
