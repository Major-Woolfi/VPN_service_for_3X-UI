import { cookies, headers } from 'next/headers';
import Header from '@/components/Header';
import { getTariffs, getStatsOverview, getPublicLinks } from '@/lib/api';
import { tServer, resolveLanguage } from '@/lib/i18n-server';
import LiveStatusBar from '@/components/LiveStatusBar';
import NodeStatus from '@/components/NodeStatus';
import TariffGridClient from '@/components/TariffGridClient';

const telegramIcon = (
  <svg width="20" height="20" fill="currentColor" viewBox="0 0 30 30">
    <path d="m20.665 3.717-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l.002.001-.314 4.692c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.434z" />
  </svg>
);

async function getTariffsServer() {
  try {
    return await getTariffs();
  } catch {
    return [];
  }
}

async function getStatsServer() {
  try {
    return await getStatsOverview();
  } catch {
    return null;
  }
}

export const revalidate = 60;

export default async function Home() {
  const [tariffs, stats] = await Promise.all([
    getTariffsServer(),
    getStatsServer(),
  ]);

  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolveLanguage(
    cookieStore.get('vpn_language')?.value,
    headerStore.get('accept-language') || undefined,
  );
  const t = (key: string, params?: Record<string, string | number>) => tServer(lang, key, params);

  const publicLinksEnv = getPublicLinks();
  const tgBotUsername = publicLinksEnv.telegram_bot_username || process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;
  const tgChannelUsername = publicLinksEnv.telegram_channel_username || process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_USERNAME;
  const tgBot = tgBotUsername ? `https://t.me/${tgBotUsername}` : null;
  const tgChannel = tgChannelUsername ? `https://t.me/${tgChannelUsername}` : null;
  const vpnName = process.env.NEXT_PUBLIC_VPN_NAME || 'vpn';

  const features_list: string[] = [];
  for (let i = 1; i <= 20; i++) {
    if (i === 2) continue;
    const text = t(`texts.feature_${i}`);
    if (text === `texts.feature_${i}`) continue;
    features_list.push(text);
  }

  return (
    <>
      <Header currentPage="/" />
      <main>
        <div className="profile">
          <div className="profile-header">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="profile-avatar" src="/icon.jpg" alt={vpnName} />
            <div className="profile-info">
              <h1 className="profile-name">{vpnName}</h1>
              <div className="profile-social">
                {tgChannel && (
                  <a href={tgChannel} target="_blank" rel="noopener noreferrer" className="social-link">
                    {telegramIcon}@{tgChannelUsername}
                  </a>
                )}
                {tgBot && (
                  <a href={tgBot} target="_blank" rel="noopener noreferrer" className="social-link">
                    {telegramIcon}@{tgBotUsername}
                  </a>
                )}
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t('texts.about')}</h2>
            <div className="pinned-content">
              <p>{t('texts.about_text')}</p>
              <p>{t('texts.about_text_2')}</p>
              <p>{t('texts.trial_available')}</p>
              <blockquote>&quot;{t('texts.quote')}&quot;</blockquote>
            </div>
          </div>

          {stats && (
            <div className="pinned-section fade-in delay-1">
              <h2>{t('texts.stats')}</h2>
              <div className="pinned-content">
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' }}>
                  <LiveStatusBar />
                </div>
                <div className="grid-auto-fit mt-4">
                  <div className="stat-card">
                    <div className="stat-value">{stats.total_users ?? 0}</div>
                    <div className="stat-label">{t('texts.all_users')}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{stats.active_subscriptions ?? 0}</div>
                    <div className="stat-label">{t('texts.active_subs')}</div>
                  </div>
                  {stats.banned_users !== undefined && stats.banned_users > 0 && (
                    <div className="stat-card">
                      <div className="stat-value">{stats.banned_users ?? 0}</div>
                      <div className="stat-label">{t('texts.banned')}</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="pinned-section fade-in delay-2">
            <h2>{t('texts.nodes')}</h2>
            <div className="pinned-content">
              <NodeStatus />
            </div>
          </div>

          {tariffs.length > 0 && (
            <div className="pinned-section fade-in delay-2">
              <h2>{t('texts.tariffs')}</h2>
              <div className="pinned-content">
                <TariffGridClient tariffs={tariffs} />
              </div>
            </div>
          )}

          <div className="contributions-section fade-in delay-3">
            <h2>{t('texts.features')}</h2>
            <div className="contributions-content">
              <ul>
                {features_list.map((feature, index) => (
                  <li key={index}>{feature}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

