import { SERVER_LANGUAGES } from "./i18n-generated";
import { normalizeServerLanguage, getServerSiteCopy } from "./i18n-server";

const siteName = process.env.NEXT_PUBLIC_VPN_NAME || "VPN";
const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "";
const languages = ["ru", "en", "de", "be", "pl", "ja", "zh"];

function replacePlaceholders(
  text: string,
  params?: Record<string, string | number>,
): string {
  const VPN_NAME = process.env.NEXT_PUBLIC_VPN_NAME || "VPN";
  let result = text.replace(/\{vpnName\}/g, VPN_NAME);
  result = result.replace(/\{siteName\}/g, VPN_NAME);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      const escapedK = k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      result = result.replace(new RegExp(`\\{${escapedK}\\}`, "g"), String(v));
    });
  }
  return result;
}

function getFAQFromTranslations(lang: string) {
  const data = SERVER_LANGUAGES[lang];
  if (!data?.qa?.category) return [];

  const sections = [];
  const qaCategory = data.qa.category as Record<string, { title?: string; content?: Record<string, { question: string; answer: string }> }>;

  for (const [categoryKey, categoryData] of Object.entries(qaCategory)) {
    if (!categoryData?.content) continue;

    const questions = [];
    for (const [, qData] of Object.entries(categoryData.content)) {
      if (qData.question && qData.answer) {
        questions.push({
          question: replacePlaceholders(qData.question),
          answer: replacePlaceholders(qData.answer),
        });
      }
    }

    if (questions.length > 0) {
      sections.push({
        title: categoryData.title || categoryKey,
        questions,
      });
    }
  }

  return sections;
}

export function generateJsonLd(
  language?: string,
  pageType: "home" | "qa" | "partner" | "client" | "tos" | "privacy" | "offer" | "login" | "register" | "profile" | "settings" | "payment" | "subscription" | "referral" | "subscribe" = "home",
  path?: string
) {
  const normalizedLanguage = normalizeServerLanguage(language);
  const copy = getServerSiteCopy(normalizedLanguage);
  const faqSections = getFAQFromTranslations(normalizedLanguage);
  const pageUrl = path ? `${baseUrl}${path}` : baseUrl;

  const faqItems = faqSections.flatMap((section) =>
    section.questions.map((q) => ({
      "@type": "Question",
      name: q.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: q.answer,
      },
    }))
  );

  const baseGraph = [
    {
      "@type": "Organization",
      "@id": `${baseUrl}/#organization`,
      name: siteName,
      url: baseUrl,
      logo: `${baseUrl}/icon.jpg`,
      foundingDate: "2026-07-07",
      sameAs: [
        "https://t.me/Phantom_OFFNET",
      ],
      contactPoint: {
        "@type": "ContactPoint",
        telephone: "",
        contactType: "customer support",
        availableLanguage: languages,
        email: "support@phantomvpn.local",
      },
    },
    {
      "@type": "WebSite",
      "@id": `${baseUrl}/#website`,
      url: baseUrl,
      name: siteName,
      description: copy.siteDescription || "VPN-сервис на базе XRay с поддержкой VLESS, Shadowsocks, REALITY, ML-KEM-768",
      publisher: { "@id": `${baseUrl}/#organization` },
      inLanguage: languages,
      potentialAction: {
        "@type": "SearchAction",
        target: {
          "@type": "EntryPoint",
          urlTemplate: `${baseUrl}/qa?search={search_term_string}`,
        },
        "query-input": "required name=search_term_string",
      },
    },
    {
      "@type": "WebPage",
      "@id": `${pageUrl}#webpage`,
      url: pageUrl,
      name: pageType === "home" ? siteName : `${copy.siteTitle || siteName}`,
      isPartOf: { "@id": `${baseUrl}/#website` },
      about: { "@id": `${baseUrl}/#organization` },
      inLanguage: normalizedLanguage,
      ...(pageType === "qa" && {
        mainEntity: { "@id": `${baseUrl}/qa#faqpage` },
      }),
    },
  ];

  const pageSpecificGraph = [];

  switch (pageType) {
    case "home":
      pageSpecificGraph.push(
        {
          "@type": "FAQPage",
          "@id": `${baseUrl}/qa#faqpage`,
          mainEntity: faqItems.slice(0, 10),
        },
        {
          "@type": "ItemList",
          "@id": `${baseUrl}#features`,
          itemListElement: Object.entries(SERVER_LANGUAGES[normalizedLanguage]?.texts || {})
            .filter(([k]) => k.startsWith("feature_"))
            .slice(0, 10)
            .map(([, v], i) => ({
              "@type": "ListItem",
              position: i + 1,
              name: replacePlaceholders(v as string),
            })),
        }
      );
      break;

    case "qa":
      pageSpecificGraph.push({
        "@type": "FAQPage",
        "@id": `${baseUrl}/qa#faqpage`,
        mainEntity: faqItems,
      });
      break;

    case "partner":
      pageSpecificGraph.push({
        "@type": "Service",
        "@id": `${baseUrl}/partner#service`,
        name: "Партнёрская программа",
        description: SERVER_LANGUAGES[normalizedLanguage]?.texts?.partner_program_text || "Партнёрская программа с гибкими бонусами",
        provider: { "@id": `${baseUrl}/#organization` },
        serviceType: "Affiliate Program",
        areaServed: "Worldwide",
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "RUB",
          availability: "https://schema.org/InStock",
        },
      });
      break;

    case "login":
    case "register":
      pageSpecificGraph.push({
        "@type": ["WebPage", "ActionAccessSpecification"],
        "@id": `${baseUrl}/${pageType}#action`,
        name: pageType === "login" ? "Вход в аккаунт" : "Регистрация",
        description: pageType === "login" 
          ? "Вход по логину/паролю или через Telegram" 
          : "Регистрация по логину и паролю с подтверждением",
      });
      break;

    case "profile":
    case "settings":
      pageSpecificGraph.push({
        "@type": "ProfilePage",
        "@id": `${baseUrl}/${pageType}#profile`,
        mainEntity: { "@id": `${baseUrl}/#organization` },
      });
      break;

    case "subscription":
    case "subscribe":
      pageSpecificGraph.push({
        "@type": "Product",
        "@id": `${baseUrl}/subscription#product`,
        name: "VPN подписка",
        description: "VPN-сервис на базе XRay с поддержкой VLESS, Shadowsocks, REALITY, ML-KEM-768, XHTTP",
        brand: { "@type": "Brand", name: siteName },
        category: "VPN Service",
        offers: {
          "@type": "AggregateOffer",
          priceCurrency: "RUB",
          lowPrice: "200",
          highPrice: "5000",
          availability: "https://schema.org/InStock",
          seller: { "@id": `${baseUrl}/#organization` },
        },
      });
      break;
  }

  pageSpecificGraph.push({
    "@type": "Product",
    "@id": `${baseUrl}/#product`,
    name: "VPN подписка",
    description: "VPN-сервис на базе XRay с поддержкой VLESS, Shadowsocks, REALITY, ML-KEM-768, XHTTP",
    brand: { "@type": "Brand", name: siteName },
    category: "VPN Service",
    offers: {
      "@type": "AggregateOffer",
      priceCurrency: "RUB",
      lowPrice: "200",
      highPrice: "5000",
      availability: "https://schema.org/InStock",
      seller: { "@id": `${baseUrl}/#organization` },
    },
  });

  pageSpecificGraph.push({
    "@type": "Service",
    "@id": `${baseUrl}/#service`,
    name: siteName,
    description: "VPN-сервис с поддержкой VLESS, Shadowsocks, REALITY, ML-KEM-768, XHTTP. Обход белых списков, No-Logs, постквантовое шифрование.",
    provider: { "@id": `${baseUrl}/#organization` },
    serviceType: "VPN",
    areaServed: "Worldwide",
    availableChannel: {
      "@type": "ServiceChannel",
      serviceUrl: baseUrl,
      servicePhone: "",
      serviceEmail: "support@phantomvpn.local",
      availableLanguage: languages,
    },
  });

  return {
    "@context": "https://schema.org",
    "@graph": [...baseGraph, ...pageSpecificGraph],
  };
}

export function generateJsonLdScript(
  language?: string,
  pageType?:
    | "home"
    | "qa"
    | "partner"
    | "client"
    | "tos"
    | "privacy"
    | "offer"
    | "login"
    | "register"
    | "profile"
    | "settings"
    | "payment"
    | "subscription"
    | "referral"
    | "subscribe"
    | undefined,
  path?: string,
) {
  return { __html: JSON.stringify(generateJsonLd(language, pageType, path)) };
}