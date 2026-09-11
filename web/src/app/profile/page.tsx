'use client';

import Link from 'next/link';
import Header from '@/components/Header';
import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/contexts/LanguageContext';
import { getSubscriptionLink } from '@/lib/api';
import type { SubscriptionLinkResponse } from '@/lib/types';
import { useFeatures } from '@/contexts/FeaturesContext';

export default function ProfilePage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const { t, lang } = useLanguage();
  const { features } = useFeatures();
  const [loading, setLoading] = useState(true);
  const [subLink, setSubLink] = useState<SubscriptionLinkResponse | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = async (text: string, type: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    }
  };

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace('/login?next=/profile');
      return;
    }

    if (user.is_admin && user.admin_subscription?.url) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSubLink({
        subscription_id: 'Admin',
        vpn_url: user.admin_subscription.url,
        json_vpn_url: user.admin_subscription.json_url || '',
        plan_text: 'Admin',
        traffic_gb: 0,
        ip_limit: 0,
        plan_servers: [],
      });
    } else if (user?.subscription?.status === 'active') {
      const aborter = new AbortController();
      getSubscriptionLink(aborter.signal)
        .then(setSubLink)
        .catch(() => setSubLink(null));
      return () => aborter.abort();
    }
    setLoading(false);
  }, [authLoading, user, router]);

  if (authLoading || loading || !user) {
    return <><Header currentPage="/profile" /><main><div className="profile"><div className="pinned-section"><p>{t('texts.loading')}</p></div></div></main></>;
  }

  const sub = user?.subscription;
  const isSubscribed = sub?.status === 'active';
  const hasAdminSub = Boolean(user?.is_admin && user?.admin_subscription?.url);
  const isAdminSub = hasAdminSub && !isSubscribed;

  const trafficUsed = sub?.used_gb || 0;
  const trafficTotal = sub?.traffic_gb || 0;
  const trafficPercent = trafficTotal > 0 ? Math.round((trafficUsed / trafficTotal) * 100) : 0;
  const expiryDate = sub?.expiry_sub_datatime || '';
  const formattedExpiry = expiryDate ? new Date(expiryDate).toLocaleDateString(lang) : '-';
  const planText = isAdminSub ? t('texts.admin_plan') : (sub?.plan_text || '-');
  const displayTrafficTotal = isAdminSub ? t('texts.unlimited') : t('texts.traffic_gb', { value: trafficTotal });
  const displayIps = isAdminSub ? t('texts.unlimited') : (sub?.ip_limit || 0);

  const initials = user?.username?.charAt(0).toUpperCase() || '?';

  return (
    <>
      <Header currentPage="/profile" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-avatar profile-avatar-placeholder">{initials}</div>
            <div className="profile-info">
              <h1 className="profile-name">{user?.username || `${t('texts.user_id')}:${user?.user_id}`}</h1>
              <p className="profile-username">{t('texts.account')}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t('texts.subscription_status')}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{t('texts.status')}:</span>
                <span style={{ color: isSubscribed || hasAdminSub ? 'var(--success)' : 'var(--text-secondary)', fontWeight: '600' }}>
                  {isSubscribed || hasAdminSub ? t('texts.status_active') : t('texts.no_subscription')}
                </span>
              </div>
            </div>
          </div>

          {!isSubscribed && !hasAdminSub ? (
            <div className="pinned-section fade-in">
              <h2>{t('texts.no_subscription')}</h2>
              <div className="pinned-content">
                <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>
                  {t('texts.no_subscription_text')}
                </p>
                <Link
                  href="/subscribe"
                  className="button"
                  style={{ display: 'inline-block', marginTop: '16px', textDecoration: 'none' }}
                >
                  {t('buttons.buy')}
                </Link>
              </div>
            </div>
          ) : (
            <>
              <div className="pinned-section fade-in">
                <h2>{t('texts.subscription_status')}</h2>
                <div className="pinned-content">
                  <div style={{ marginTop: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('texts.status_active')}</span>
                      <span style={{ color: 'var(--success)', fontWeight: '600' }}>{t('texts.status_active')}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('texts.plan')}</span>
                      <span>{planText}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('texts.expires')}</span>
                      <span>{formattedExpiry}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('texts.traffic')}</span>
                       <span>{t('texts.traffic_gb', { value: trafficUsed })} / {displayTrafficTotal}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('texts.ips')}</span>
                      <span>{displayIps}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{t('texts.trust_score')}</span>
                      <span>{user?.trust_score || 0} ({user?.discount_percent || 0}% {t('texts.discount')})</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pinned-section fade-in delay-1">
                <h2>{t('texts.traffic_progress')}</h2>
                <div className="pinned-content">
                  <div style={{ marginTop: '16px' }}>
                    <div style={{ height: '24px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${trafficPercent}%`, background: trafficPercent > 80 ? 'var(--danger)' : 'linear-gradient(90deg, var(--accent), var(--accent-hover))', borderRadius: 'var(--radius-sm)', transition: 'width 0.3s ease' }} />
                    </div>
                    <p style={{ marginTop: '8px', fontSize: '14px', color: 'var(--text-secondary)' }}>
                      {t('texts.traffic_used', { percent: trafficPercent, total: trafficTotal })}
                    </p>
                  </div>
                </div>
              </div>

              {(isSubscribed || (user?.is_admin && user?.admin_subscription?.url)) && subLink && (
                <div className="pinned-section fade-in delay-2">
                  <h2>{t('texts.subscription_link')}</h2>
                  <div className="pinned-content">
                    <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontFamily: 'monospace', fontSize: '14px', wordBreak: 'break-all', display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <code style={{ flex: 1 }}>{subLink?.vpn_url}</code>
                        <button
                          onClick={() => handleCopy(subLink!.vpn_url, 'vpn')}
                          className="button"
                          style={{ whiteSpace: 'nowrap', padding: '6px 12px' }}
                        >
                          {copied === 'vpn' ? t('buttons.copied') : t('buttons.copy')}
                        </button>
                      </div>
                      {subLink?.json_vpn_url && (
                        <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontFamily: 'monospace', fontSize: '14px', wordBreak: 'break-all', display: 'flex', gap: '8px', alignItems: 'center' }}>
                          <code style={{ flex: 1 }}>{subLink.json_vpn_url}</code>
                          <button
                            onClick={() => handleCopy(subLink!.json_vpn_url!, 'json')}
                            className="button"
                            style={{ whiteSpace: 'nowrap', padding: '6px 12px' }}
                          >
                            {copied === 'json' ? t('buttons.copied') : t('buttons.copy')}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {user?.is_partner && user.partner_subscription?.url && features?.panel_types?.main && (
                <div className="pinned-section fade-in delay-2">
                  <h2>{t('texts.partner_subscription')}</h2>
                  <div className="pinned-content">
                    <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontFamily: 'monospace', fontSize: '14px', wordBreak: 'break-all' }}>
                        {user.partner_subscription.url}
                      </div>
                      <div style={{ padding: '12px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', fontFamily: 'monospace', fontSize: '14px', wordBreak: 'break-all' }}>
                        {user.partner_subscription.json_url}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="pinned-section fade-in delay-3">
                <h2>{t('texts.actions')}</h2>
                <div className="pinned-content">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                    {(isSubscribed || user?.admin_subscription?.url) && (
                      <Link href="/client" className="button" style={{ display: 'block', textAlign: 'center', textDecoration: 'none' }}>
                        {t('texts.setup_client')}
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </>
  );
}

