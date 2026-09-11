'use client';

import Header from '@/components/Header';
import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getReferralStats } from '@/lib/api';
import type { ReferralStatsResponse } from '@/lib/types';
import { useLanguage } from '@/contexts/LanguageContext';
import { useRouter } from 'next/navigation';

export default function ReferralPage() {
  const { loading: authLoading, user } = useAuth();
  const router = useRouter();
  const { t } = useLanguage();
  const [stats, setStats] = useState<ReferralStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login?next=/referral'); return; }
    if (user?.is_admin) { router.replace('/profile'); return; }
    (async () => {
      try {
        const data = await getReferralStats();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('texts.error'));
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, router, user, user?.is_admin, t]);

  const handleCopy = async () => {
    if (!stats?.ref_link) return;
    try {
      await navigator.clipboard.writeText(stats.ref_link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(t('texts.error'));
    }
  };

  if (authLoading || loading || !user) {
    return (
      <>
        <Header currentPage="/referral" />
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
        <Header currentPage="/referral" />
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

  const tgBotUsername = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME;

  return (
    <>
      <Header currentPage="/referral" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.referral_program')}</h1>
              <p className="profile-username">{t('texts.referral_program_text')}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t('texts.how_it_works')}</h2>
            <div className="pinned-content">
              <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>
                {t('texts.how_it_works_text', { days: stats?.bonus_days_per_paid || 7 })}
              </p>
            </div>
          </div>

          {stats && (
            <div className="pinned-section fade-in delay-1">
              <h2>{t('texts.your_ref_link')}</h2>
              <div className="pinned-content">
                <div
                  style={{ marginTop: '16px', display: 'flex', gap: '12px', alignItems: 'center' }}
                >
                  <div
                    style={{
                      flex: 1,
                      padding: '12px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-sm)',
                      fontFamily: 'monospace',
                      fontSize: '14px',
                      wordBreak: 'break-all',
                    }}
                  >
                    {tgBotUsername
                      ? `https://t.me/${tgBotUsername}?start=${stats.ref_code}`
                      : t('texts.referral_link_unavailable')}
                  </div>
                  <button onClick={handleCopy} className="button" style={{ whiteSpace: 'nowrap' }}>
                    {copied ? t('buttons.copied') : t('buttons.referral_copy')}
                  </button>
                </div>
              </div>
            </div>
          )}

          {stats && (
            <div className="pinned-section fade-in delay-2">
              <h2>{t('texts.stats')}</h2>
              <div className="pinned-content">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                    gap: '16px',
                    marginTop: '16px',
                  }}
                >
                  <div
                    style={{
                      padding: '20px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-md)',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '28px', fontWeight: '700', color: 'var(--accent)' }}>
                      {stats.total_refs || 0}
                    </div>
                    <div
                      style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '8px' }}
                    >
                      {t('texts.total_refs')}
                    </div>
                  </div>
                  <div
                    style={{
                      padding: '20px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-md)',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '28px', fontWeight: '700', color: 'var(--success)' }}>
                      {stats.paid_refs || 0}
                    </div>
                    <div
                      style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '8px' }}
                    >
                      {t('texts.paid_refs')}
                    </div>
                  </div>
                  <div
                    style={{
                      padding: '20px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: 'var(--radius-md)',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '28px', fontWeight: '700', color: 'var(--warning)' }}>
                      {stats.bonus_days_per_paid || 0}
                    </div>
                    <div
                      style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '8px' }}
                    >
                      {t('texts.bonus_days')}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
