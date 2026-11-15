export const getSsiteName = (): string => {
  const envName =
    typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_VPN_NAME
      ? process.env.NEXT_PUBLIC_VPN_NAME
      : undefined;
  return envName && envName.trim().length > 0
    ? envName.trim()
    : "VPN Service";
};

export const getSsiteUrl = (): string => {
  const envUrl =
    typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_SITE_URL
      ? process.env.NEXT_PUBLIC_SITE_URL
      : undefined;
  return envUrl && envUrl.trim().length > 0 ? envUrl.trim() : "https://vpn.local";
}






