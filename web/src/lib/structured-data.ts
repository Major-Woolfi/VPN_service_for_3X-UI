const siteName = process.env.NEXT_PUBLIC_VPN_NAME || 'VPN';
const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || '';

export function generateJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${baseUrl}/#organization`,
        name: siteName,
        url: baseUrl,
        logo: `${baseUrl}/icon.jpg`,
        foundingDate: '2026-07-07',
      },
      {
        '@type': 'WebSite',
        '@id': `${baseUrl}/#website`,
        url: baseUrl,
        name: siteName,
        description: 'VPN service with VLESS, VMess, Trojan, Shadowsocks, Hysteria, Reality protocols',
        publisher: {
          '@id': `${baseUrl}/#organization`,
        },
        inLanguage: ['ru', 'en', 'pl', 'zh', 'be', 'de', 'ja'],
      },
      {
        '@type': 'WebPage',
        '@id': `${baseUrl}/#webpage`,
        url: baseUrl,
        name: `${siteName} - Secure VPN Service`,
        isPartOf: {
          '@id': `${baseUrl}/#website`,
        },
        about: {
          '@id': `${baseUrl}/#organization`,
        },
      },
    ],
  };
}

export function generateJsonLdScript() {
  return { __html: JSON.stringify(generateJsonLd()) };
}
