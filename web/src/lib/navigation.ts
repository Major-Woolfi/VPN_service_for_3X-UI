import { useLanguage } from '@/contexts/LanguageContext';
import { useFeatures } from '@/contexts/FeaturesContext';
import { useAuth } from '@/contexts/AuthContext';
import { getPublicLinks } from '@/lib/api';

interface NavLink {
  href: string;
  labelKey: string;
  labelSection?: 'buttons' | 'texts';
  condition?: () => boolean;
  external?: boolean;
}

const publicNavLinks: NavLink[] = [
  { href: '/', labelKey: 'main' },
  { href: '/qa', labelKey: 'qa' },
  { href: '/tos', labelKey: 'tos' },
  { href: '/offer', labelKey: 'offer' },
  { href: '/privacy', labelKey: 'privacy' },
  { href: '/partner', labelKey: 'partner' },
];

const authorizedNavLinks: NavLink[] = [
  { href: '/subscribe', labelKey: 'buy' },
  { href: '/profile', labelKey: 'account', labelSection: 'texts' },
  { href: '/client', labelKey: 'client' },
  { href: '/referral', labelKey: 'referral', condition: () => false },
  { href: '/settings', labelKey: 'settings' },
];

const adminNavLinks: NavLink[] = [
  { href: '/admin/health', labelKey: 'admin_panel', labelSection: 'texts' },
];

export function useNavigation() {
  const { t } = useLanguage();
  const { features } = useFeatures();
  const { user } = useAuth();

  const getLabel = (link: NavLink) => {
    const section = link.labelSection || 'buttons';
    return t(`${section}.${link.labelKey}`);
  };

  const publicLinks = publicNavLinks
    .filter((link) => {
      if (link.href === '/partner') {
        return features?.features?.partner === true;
      }
      return true;
    })
    .map((link) => ({
      href: link.href,
      label: getLabel(link),
    }));

  const authorizedLinks = authorizedNavLinks
    .filter((link) => {
      if (link.href === '/subscribe') {
        return user?.subscription?.status !== 'active';
      }
      if (link.href === '/client') {
        return user?.subscription?.status === 'active' || user?.admin_subscription?.url;
      }
      if (link.href === '/referral') {
        return !user?.is_admin;
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

  const adminLinks = user?.is_admin
    ? adminNavLinks.map((link) => ({
        href: link.href,
        label: getLabel(link),
      }))
    : [];

  const publicLinksEnv = getPublicLinks();
  const contactLinks = [
    { href: publicLinksEnv.support_url, label: t('buttons.support') },
    {
      href: publicLinksEnv.telegram_bot_username
        ? `https://t.me/${publicLinksEnv.telegram_bot_username}`
        : process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
          ? `https://t.me/${process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME}`
          : undefined,
      label: t('buttons.open_bot'),
    },
    { href: publicLinksEnv.telegram_chat_url, label: t('buttons.telegram_chat') },
    { href: publicLinksEnv.tiktok_url, label: t('buttons.tiktok') },
    { href: publicLinksEnv.youtube_url, label: t('buttons.youtube') },
  ].filter((link): link is { href: string; label: string } => Boolean(link.href));

  return {
    publicLinks,
    authorizedLinks,
    adminLinks,
    contactLinks,
  };
}
