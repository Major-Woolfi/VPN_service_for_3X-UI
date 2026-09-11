'use client';

import Header from '@/components/Header';
import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getSubscriptionLink } from '@/lib/api';
import type { SubscriptionLinkResponse } from '@/lib/types';
import { useLanguage } from '@/contexts/LanguageContext';
import { useRouter } from 'next/navigation';

export default function ClientPage() {
  const { loading: authLoading, user } = useAuth();
  const router = useRouter();
  const { t } = useLanguage();
  const [subLink, setSubLink] = useState<SubscriptionLinkResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login?next=/client'); return; }
    if (user?.subscription?.status !== 'active' && !user?.admin_subscription?.url) {
      router.replace('/profile');
      return;
    }

    (async () => {
      try {
        const link = await getSubscriptionLink();
        setSubLink(link);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('texts.error'));
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, router, t, user, user?.subscription?.status, user?.admin_subscription?.url]);

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

  if (authLoading || loading || !user) {
    return (
      <>
        <Header currentPage="/client" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t('texts.loading')}</h1>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Header currentPage="/client" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t('texts.error')}</h1>
                <p style={{ color: 'var(--danger)' }}>{error}</p>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  const clientApp = process.env.NEXT_PUBLIC_CLIENT_APP_URL || '';
  const setupGuide = process.env.NEXT_PUBLIC_SETUP_GUIDE_URL || '';
  const supportUrl = process.env.NEXT_PUBLIC_TELEGRAM_SUPPORT || '';

  return (
    <>
      <Header currentPage="/client" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.client_setup')}</h1>
              <p className="profile-username">{t('texts.client_setup_text')}</p>
            </div>
          </div>

          {subLink && (
            <div className="pinned-section fade-in">
              <h2>{t('texts.subscription_link')}</h2>
              <div className="pinned-content">
                <div
                  style={{
                    marginTop: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                  }}
                >
                  <div
                    style={{
                      padding: '12px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-sm)',
                      fontFamily: 'monospace',
                      fontSize: '14px',
                      wordBreak: 'break-all',
                      display: 'flex',
                      gap: '8px',
                      alignItems: 'center',
                    }}
                  >
                    <code style={{ flex: 1 }}>{subLink.vpn_url}</code>
                    <button
                      onClick={() => handleCopy(subLink.vpn_url, 'vpn')}
                      className="button"
                      style={{ whiteSpace: 'nowrap', padding: '6px 12px' }}
                    >
                      {copied === 'vpn' ? t('buttons.copied') : t('buttons.copy')}
                    </button>
                  </div>
                  <div
                    style={{
                      padding: '12px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-sm)',
                      fontFamily: 'monospace',
                      fontSize: '14px',
                      wordBreak: 'break-all',
                      display: 'flex',
                      gap: '8px',
                      alignItems: 'center',
                    }}
                  >
                    <code style={{ flex: 1 }}>{subLink.json_vpn_url}</code>
                    <button
                      onClick={() => handleCopy(subLink.json_vpn_url, 'json')}
                      className="button"
                      style={{ whiteSpace: 'nowrap', padding: '6px 12px' }}
                    >
                      {copied === 'json' ? t('buttons.copied') : t('buttons.copy')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="pinned-section fade-in delay-1">
            <h2>{t('texts.recommended_apps')}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: '16px' }}>
                <h3>{t('texts.main_client')}</h3>
                <p>
                  <strong>{t('texts.main_client_text')}</strong>
                </p>
                <a
                  href={clientApp}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="button"
                  style={{ display: 'inline-block', marginTop: '8px', textDecoration: 'none' }}
                >
                  {t('buttons.download_app')}
                </a>

                <h3>{t('texts.alt_client')}</h3>
                <p>{t('texts.alt_client_text')}</p>

                <h3 style={{ marginTop: '24px' }}>{t('texts.important')}</h3>
                <blockquote>{t('texts.important_text')}</blockquote>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-1">
            <h2>{t('texts.platforms')}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: '16px' }}>
                <ul>
                  <li>
                    <strong>Android</strong> - {t('texts.platform_android')}
                  </li>
                  <li>
                    <strong>iOS</strong> - {t('texts.platform_ios')}
                  </li>
                  <li>
                    <strong>Windows</strong> - {t('texts.platform_windows')}
                  </li>
                  <li>
                    <strong>macOS</strong> - {t('texts.platform_macos')}
                  </li>
                  <li>
                    <strong>Linux</strong> - {t('texts.platform_linux')}
                  </li>
                  <li>
                    <strong>Android TV</strong> - {t('texts.platform_android_tv')}
                  </li>
                   <li>
                     <strong>{t('texts.platform_router_name')}</strong> - {t('texts.platform_router')}
                   </li>
                </ul>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-2">
            <h2>{t('texts.steps')}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: '16px' }}>
                <ol style={{ paddingLeft: '20px' }}>
                  <li style={{ marginBottom: '12px' }}>{t('texts.step_1')}</li>
                  <li style={{ marginBottom: '12px' }}>{t('texts.step_2')}</li>
                  <li style={{ marginBottom: '12px' }}>{t('texts.step_3')}</li>
                  <li style={{ marginBottom: '12px' }}>{t('texts.step_4')}</li>
                  <li>{t('texts.step_5')}</li>
                </ol>
                <p style={{ marginTop: '16px' }}>
                  {t('texts.guide_available')}{' '}
                  <a href={setupGuide} target="_blank" rel="noopener noreferrer">
                    {t('texts.guide_link')}
                  </a>
                </p>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-3">
            <h2>{t('texts.need_help')}</h2>
            <div className="pinned-content">
              <p>
                {t('texts.need_help_text')}{' '}
                {supportUrl ? (
                  <a href={supportUrl} target="_blank" rel="noopener noreferrer">
                    {t('buttons.support')}
                  </a>
                ) : (
                  t('texts.support_unavailable')
                )}
              </p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
