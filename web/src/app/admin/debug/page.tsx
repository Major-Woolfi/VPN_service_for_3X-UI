'use client';

import Header from '@/components/Header';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { debugCleanup, debugSearch, getAbuseUsers, clearAbuse } from '@/lib/api';
import type { AbuseUser, AbuseUsersResponse } from '@/lib/types';
import type { DebugSearchResponse } from '@/lib/types';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';

export default function AdminDebugPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<DebugSearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [abuseUsers, setAbuseUsers] = useState<AbuseUser[] | null>(null);
  const [abuseLoading, setAbuseLoading] = useState(false);
  const { loading: authLoading, user: authUser } = useAuth();
  const router = useRouter();
  const { t } = useLanguage();

  useEffect(() => {
    if (!authLoading && !authUser) {
      router.replace('/login?next=/admin/debug');
      return;
    }
    if (authUser && !authUser.is_admin) {
      router.replace('/profile');
      return;
    }
  }, [authLoading, router, authUser]);

  const handleCleanup = async (dryRun: boolean) => {
    if (!authUser) return;

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const data = await debugCleanup({
        dry_run: dryRun,
        cleanup_expired: true,
        cleanup_traffic_exhausted: true,
        cleanup_missing: true,
      });
      setResult(data as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!authUser || !searchQuery.trim()) return;

    setSearchLoading(true);
    setError('');
    setSearchResults(null);

    try {
      const data = await debugSearch(searchQuery.trim());
      setSearchResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.error'));
    } finally {
      setSearchLoading(false);
    }
  };

  const handleLoadAbuseUsers = async () => {
    setAbuseLoading(true);
    setError('');
    try {
      const data = await getAbuseUsers();
      setAbuseUsers(data.users);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setAbuseLoading(false);
    }
  };

  const handleClearAbuse = async (userId: number) => {
    try {
      await clearAbuse({ user_id: userId, reason: 'Manual clear' });
      setAbuseUsers(abuseUsers ? abuseUsers.filter(u => u.user_id !== userId) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  };

  return (
    <>
      <Header currentPage="/admin/debug" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.debug')}</h1>
              <p className="profile-username">{t('texts.debug_subtitle')}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t('texts.cleanup_subs')}</h2>
            <div className="pinned-content">
              <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>
                {t('texts.cleanup_text')}
              </p>
              <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                <button
                  onClick={() => handleCleanup(true)}
                  className="button"
                  disabled={loading}
                  style={{ flex: 1 }}
                >
                  {t('buttons.dry_run')}
                </button>
                <button
                  onClick={() => handleCleanup(false)}
                  className="button"
                  disabled={loading}
                  style={{ flex: 1, background: 'var(--danger)' }}
                >
                  {loading ? t('texts.processing') : t('buttons.cleanup')}
                </button>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-1">
            <h2>{t('texts.debug_search')}</h2>
            <div className="pinned-content">
              <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>
                {t('texts.debug_search_description')}
              </p>
              <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder={t('texts.debug_search_placeholder')}
                  className="faq-search-input"
                  style={{ flex: 1 }}
                />
                <button
                  onClick={handleSearch}
                  className="button"
                  disabled={searchLoading}
                  style={{ flex: '0 0 auto' }}
                >
                  {searchLoading ? t('texts.loading') : t('buttons.search')}
                </button>
              </div>
            </div>
          </div>

          {error && (
            <div className="pinned-section fade-in delay-1">
              <h2>{t('texts.error')}</h2>
              <div className="pinned-content">
                <p style={{ color: 'var(--danger)', marginTop: '16px' }}>{error}</p>
              </div>
            </div>
          )}

          {searchResults && (
            <div className="pinned-section fade-in delay-2">
              <h2>
                {t('texts.search_results_count', { count: searchResults.count })}
              </h2>
              <div className="pinned-content">
                {searchResults.users.length === 0 ? (
                  <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>
                    {t('texts.search_no_results')}
                  </p>
                ) : (
                  <div style={{ overflowX: 'auto', marginTop: '16px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_uid')}</th>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_username')}</th>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_telegram_id')}</th>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_login')}</th>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_vpn_url')}</th>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_trust')}</th>
                          <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_banned')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {searchResults.users.map((u) => (
                          <tr key={u.user_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                            <td style={{ padding: '12px' }}>{u.user_id}</td>
                            <td style={{ padding: '12px' }}>{u.username || '-'}</td>
                            <td style={{ padding: '12px' }}>{u.telegram_id || '-'}</td>
                            <td style={{ padding: '12px' }}>{u.login || '-'}</td>
                            <td style={{ padding: '12px' }}>{u.subscription?.vpn_url || '-'}</td>
                            <td style={{ padding: '12px' }}>{u.trust_score}</td>
                            <td style={{ padding: '12px' }}>{u.banned ? t('texts.yes') : t('texts.no')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {result && (
            <div className="pinned-section fade-in delay-2">
              <h2>{t('texts.result')}</h2>
              <div className="pinned-content">
                <pre
                  style={{
                    marginTop: '16px',
                    padding: '16px',
                    background: 'var(--bg-tertiary)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '14px',
                    overflowX: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            </div>
          )}
        <div className="pinned-section fade-in delay-3">
          <h2>ABUSE Users</h2>
          <div className="pinned-content">
            <button
              onClick={handleLoadAbuseUsers}
              disabled={abuseLoading}
              style={{
                padding: '8px 16px',
                background: 'var(--accent)',
                color: '#fff',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
                fontSize: '14px',
              }}
            >
              {abuseLoading ? 'Loading...' : 'Load ABUSE Users'}
            </button>
            {abuseUsers && abuseUsers.length > 0 && (
              <div style={{ marginTop: '16px', overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                      <th style={{ padding: '8px', textAlign: 'left' }}>ID</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Username</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Status</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Daily GB</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Total GB</th>
                      <th style={{ padding: '8px', textAlign: 'left' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {abuseUsers.map((u) => (
                      <tr key={u.user_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '8px' }}>{u.user_id}</td>
                        <td style={{ padding: '8px' }}>{u.username}</td>
                        <td style={{ padding: '8px' }}>
                          <span style={{
                            padding: '4px 8px',
                            background: 'var(--danger)',
                            borderRadius: 'var(--radius-sm)',
                            color: '#fff',
  fontSize: '12px',
                          }}>
                            {u.abuse_status}
                          </span>
                        </td>
                        <td style={{ padding: '8px' }}>{u.daily_traffic_gb.toFixed(2)}</td>
                        <td style={{ padding: '8px' }}>{u.total_traffic_gb.toFixed(2)}</td>
                        <td style={{ padding: '8px' }}>
                          <button
                            onClick={() => handleClearAbuse(u.user_id)}
                            style={{
                              padding: '4px 12px',
                              background: 'var(--success)',
                              color: '#fff',
                              border: 'none',
                              borderRadius: 'var(--radius-sm)',
                              cursor: 'pointer',
                              fontSize: '12px',
                            }}
                          >
                            Clear
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
        </div>
      </main>
    </>
  );
}

