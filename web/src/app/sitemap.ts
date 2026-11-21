import { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://vpn.local";
  const lastModified = new Date().toISOString().slice(0, 10);

  const routes: Array<{
    url: string;
    priority: number;
    changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"];
  }> = [
    { url: "/", priority: 1.0, changeFrequency: "weekly" },
    { url: "/subscribe", priority: 0.9, changeFrequency: "weekly" },
    { url: "/partner", priority: 0.8, changeFrequency: "monthly" },
    { url: "/client", priority: 0.7, changeFrequency: "monthly" },
    { url: "/referral", priority: 0.6, changeFrequency: "monthly" },
    { url: "/qa", priority: 0.8, changeFrequency: "monthly" },
    { url: "/tos", priority: 0.5, changeFrequency: "monthly" },
    { url: "/privacy", priority: 0.5, changeFrequency: "monthly" },
    { url: "/offer", priority: 0.4, changeFrequency: "monthly" },
  ];

  return routes.map((route) => ({
    url: `${baseUrl}${route.url}`,
    lastModified,
    changeFrequency: route.changeFrequency,
    priority: route.priority,
  }));
}
