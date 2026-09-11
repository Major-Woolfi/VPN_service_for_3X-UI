'use client';

import Header from '@/components/Header';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getUsers } from '@/lib/api';
import type { UserListResponse } from '@/lib/types';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserListResponse['users']>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const { loading: authLoading, user: authUser } = useAuth();
  const router = useRouter();
  const { t } = useLanguage();

  const limit = 50;

  const loadUsers = useCallback(async () => {
    if (!authUser?.is_admin) return;
    setLoading(true);
    try {
      const data = await getUsers(page, limit);
      setUsers(data.users);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.error'));
    } finally {
      setLoading(false);
    }
  }, [authUser, page, t]);

  useEffect(() => {
    if (authLoading) return;
    if (!authUser) {
      router.replace('/login?next=/admin/users');
      return;
    }
    if (!authUser.is_admin) {
      router.replace('/profile');
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadUsers();
  }, [authLoading, router, loadUsers, authUser]);

  const filteredUsers = searchTerm
    ? users.filter(
        (u) =>
          u.user_id.toString().includes(searchTerm) ||
          (u.username || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
          u.telegram_id.toString().includes(searchTerm)
      )
    : users;

  if (loading) {
    return (
      <>
        <Header currentPage="/admin/users" />
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
        <Header currentPage="/admin/users" />
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

  const totalPages = Math.ceil(total / limit);

  return (
    <>
      <Header currentPage="/admin/users" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.users_list')}</h1>
              <p className="profile-username">
                {t('texts.users_count')} ({total})
              </p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div style={{ marginTop: '16px', marginBottom: '16px' }}>
                <input
                  type="text"
                  placeholder={t('texts.search_placeholder')}
                  className="faq-search-input"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              <div style={{ overflowX: 'auto', marginTop: '16px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                      <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_uid')}</th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_username')}</th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>{t('texts.admin_user_telegram_id')}</th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>
                        {t('texts.subscription_status')}
                      </th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>{t('buttons.partner')}</th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>
                        {t('texts.trust_score')}
                      </th>
                      <th style={{ padding: '12px', textAlign: 'left' }}>ABUSE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((u) => (
                      <tr key={u.user_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '12px' }}>{u.user_id}</td>
                        <td style={{ padding: '12px' }}>{u.username || '-'}</td>
                        <td style={{ padding: '12px' }}>{u.telegram_id || '-'}</td>
                        <td style={{ padding: '12px' }}>
                          <span
                            style={{
                              padding: '4px 8px',
                              background: u.has_subscription
                                ? 'var(--success)'
                                : 'var(--bg-tertiary)',
                              borderRadius: 'var(--radius-sm)',
                              color: u.has_subscription ? '#fff' : 'var(--text-secondary)',
                              fontSize: '12px',
                            }}
                          >
                            {u.has_subscription ? t('texts.status_active') : t('texts.no')}
                          </span>
                        </td>
                        <td style={{ padding: '12px' }}>
                          <span
                            style={{
                              padding: '4px 8px',
                              background: u.is_mate ? 'var(--accent)' : 'var(--bg-tertiary)',
                              borderRadius: 'var(--radius-sm)',
                              color: u.is_mate ? '#fff' : 'var(--text-secondary)',
                              fontSize: '12px',
                            }}
                          >
                            {u.is_mate ? t('texts.yes') : t('texts.no')}
                          </span>
                        </td>
                        <td style={{ padding: '12px' }}>{u.trust_score}</td>
                        <td style={{ padding: '12px' }}>
                          {u.abuse_status ? (
                            <span style={{
                              padding: '4px 8px',
                              background: 'var(--danger)',
                              borderRadius: 'var(--radius-sm)',
                              color: '#fff',
                              fontSize: '12px',
                            }}>
                              {u.abuse_status}
                            </span>
                          ) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div
                style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '24px' }}
              >
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="button"
                  style={{ opacity: page === 1 ? 0.5 : 1 }}
                >
                  {t('buttons.back')}
                </button>
                <span style={{ padding: '12px', fontSize: '14px' }}>
                  {t('texts.page_of', { page, total: totalPages })}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="button"
                  style={{ opacity: page === totalPages ? 0.5 : 1 }}
                >
                  {t('buttons.forward')}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

