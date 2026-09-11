import { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || '';
  const lastModified = new Date().toISOString().split('T')[0];

  const routes = [
    { url: '/', priority: 1.0, changefreq: 'weekly' as const },
    { url: '/subscribe', priority: 0.9, changefreq: 'weekly' as const },
    { url: '/partner', priority: 0.8, changefreq: 'monthly' as const },
    { url: '/client', priority: 0.7, changefreq: 'monthly' as const },
    { url: '/referral', priority: 0.6, changefreq: 'monthly' as const },
    { url: '/qa', priority: 0.8, changefreq: 'monthly' as const },
    { url: '/tos', priority: 0.5, changefreq: 'monthly' as const },
    { url: '/privacy', priority: 0.5, changefreq: 'monthly' as const },
    { url: '/offer', priority: 0.4, changefreq: 'monthly' as const },
  ];

  return routes.map((route) => ({
    url: `${baseUrl}${route.url}`,
    lastModified,
    changeFrequency: route.changefreq,
    priority: route.priority,
  }));
}
