import { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "";
  const lastModified = "2026-11-02";
  const languages = ["ru", "en", "de", "be", "pl", "ja", "zh"];

  const routes = [
    { url: "/", priority: 1.0, changefreq: "weekly" as const },
    { url: "/subscribe", priority: 0.9, changefreq: "weekly" as const },
    { url: "/partner", priority: 0.8, changefreq: "monthly" as const },
    { url: "/client", priority: 0.7, changefreq: "monthly" as const },
    { url: "/referral", priority: 0.6, changefreq: "monthly" as const },
    { url: "/qa", priority: 0.8, changefreq: "monthly" as const },
    { url: "/tos", priority: 0.5, changefreq: "monthly" as const },
    { url: "/privacy", priority: 0.5, changefreq: "monthly" as const },
    { url: "/offer", priority: 0.4, changefreq: "monthly" as const },
    { url: "/login", priority: 0.3, changefreq: "monthly" as const },
    { url: "/register", priority: 0.3, changefreq: "monthly" as const },
    { url: "/settings", priority: 0.2, changefreq: "monthly" as const },
    { url: "/profile", priority: 0.2, changefreq: "monthly" as const },
    { url: "/payment", priority: 0.2, changefreq: "monthly" as const },
    { url: "/subscription", priority: 0.2, changefreq: "monthly" as const },
    { url: "/subscribe", priority: 0.9, changefreq: "weekly" as const },
  ];

  const sitemapEntries: MetadataRoute.Sitemap = [];

  for (const route of routes) {
    const url = `${baseUrl}${route.url}`;

    // Default language entry (x-default)
    sitemapEntries.push({
      url,
      lastModified,
      changeFrequency: route.changefreq,
      priority: route.priority,
      alternates: {
        languages: Object.fromEntries(
          languages.map((lang) => [lang, `${baseUrl}/${lang}${route.url}`]),
        ),
      },
    });

    // Language-specific entries
    for (const lang of languages) {
      sitemapEntries.push({
        url: `${baseUrl}/${lang}${route.url}`,
        lastModified,
        changeFrequency: route.changefreq,
        priority: route.priority,
      });
    }
  }

  // Add icon image
  sitemapEntries.push({
    url: `${baseUrl}/icon.jpg`,
    lastModified,
    changeFrequency: "yearly" as const,
    priority: 0.1,
  });

  return sitemapEntries;
}
