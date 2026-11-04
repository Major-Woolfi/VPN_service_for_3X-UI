export const getSiteName = (): string => {
  const envName =
    typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_VPN_NAME
      ? process.env.NEXT_PUBLIC_VPN_NAME
      : undefined;
  return envName && envName.trim().length > 0
    ? envName.trim()
    : "VPN Service";
};

export const getSiteUrl = (): string => {
  const envUrl =
    typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_SITE_URL
      ? process.env.NEXT_PUBLIC_SITE_URL
      : undefined;
  return envUrl && envUrl.trim().length > 0 ? envUrl.trim() : "https://vpn.local";
}

export const getSeoBaseConfig = (): {
  siteName: string;
  siteUrl: string;
  description: string;
} => {
  const name = getSiteName();
  const url = getSiteUrl();
  const description = `${name} - современный VPN-сервис с поддержкой VLESS, Shadowsocks, REALITY, ML-KEM-768, обходом блокировок и защитой без логов.`;
  return { siteName: name, siteUrl: url, description };
};
