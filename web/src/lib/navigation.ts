import { useLanguage } from "@/contexts/LanguageContext";
import { useFeatures } from "@/contexts/FeaturesContext";
import { useAuth } from "@/contexts/AuthContext";
import { getPublicLinksFromFeatures } from "@/lib/api";

interface Navlink {
  href: string;
  labelkey: string;
  labelsection?: "buttons" | "texts";
  condition?: () => boolean;
  external?: boolean;
}

const publicNavlinks: Navlink[] = [
  { href: "/", labelkey: "main" },
  { href: "/qa", labelkey: "qa" },
  { href: "/tos", labelkey: "tos" },
  { href: "/offer", labelkey: "offer" },
  { href: "/privacy", labelkey: "privacy" },
  { href: "/partner", labelkey: "partner" },
];

const authorizedNavlinks: Navlink[] = [
  { href: "/subscribe", labelkey: "buy" },
  { href: "/profile", labelkey: "account", labelsection: "texts" },
  { href: "/client", labelkey: "client" },
  { href: "/referral", labelkey: "referral" },
  { href: "/co-owners", labelkey: "co_owners" },
  { href: "/co-owners/stats", labelkey: "co_owner_stats", labelsection: "texts" },
  { href: "/settings", labelkey: "settings" },
];

const adminNavlinks: Navlink[] = [
  { href: "/admin/health", labelkey: "admin_panel", labelsection: "texts" },
  { href: "/admin/users", labelkey: "all_users", labelsection: "texts" },
];

export function useNavigation() {
  const { t } = useLanguage();
  const { features } = useFeatures();
  const { user } = useAuth();

  const getLabel = (link: Navlink) => {
    const section = link.labelsection || "buttons";
    return t(`${section}.${link.labelkey}`);
  };

  const publiclinks = publicNavlinks
    .filter((link) => {
      if (link.href === "/partner") {
        return features?.features?.partner === true;
      }
      return true;
    })
    .map((link) => ({
      href: link.href,
      label: getLabel(link),
    }));

  const authorizedlinks = authorizedNavlinks
    .filter((link) => {
      if (link.href === "/subscribe") {
        return user?.subscription?.status !== "active" || user.is_admin;
      }
      if (link.href === "/client") {
        return user?.subscription?.status === "active" || user?.admin_subscription?.url;
      }
      if (link.href === "/referral") {
        return !user?.is_admin && Boolean(user?.referral?.ref_code || user?.is_partner);
      }
      if (link.href === "/co-owners" || link.href === "/co-owners/stats") {
        return Boolean(user?.is_coowner);
      }
      if (link.condition) {
        return link.condition();
      }
      return true;
    })
    .map((link) => ({
      href: link.href,
      label: getLabel(link),
    }));

  const adminlinks = user?.is_admin
    ? adminNavlinks.map((link) => ({
        href: link.href,
        label: getLabel(link),
      }))
    : [];

  const publicLinksEnv = getPublicLinksFromFeatures(features);
  const contactlinks = [
    { href: publicLinksEnv.support_url, label: t("buttons.contact_support") },
    {
      href: publicLinksEnv.telegram_bot_username
        ? `https://t.me/${publicLinksEnv.telegram_bot_username}`
        : publicLinksEnv.telegram_url,
      label: t("buttons.open_bot"),
    },
    {
      href: publicLinksEnv.telegram_chat_url,
      label: t("buttons.telegram_chat"),
    },
    { href: publicLinksEnv.tiktok_url, label: t("buttons.tiktok") },
    { href: publicLinksEnv.youtube_url, label: t("buttons.youtube") },
  ].filter((link): link is { href: string; label: string } => Boolean(link.href));

  return {
    publiclinks,
    authorizedlinks,
    adminlinks,
    contactlinks,
  };
}
