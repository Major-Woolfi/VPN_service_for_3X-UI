'use client';

import Header from '@/components/Header';
import Link from 'next/link';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { loginUser, startTelegramAuth, pollTelegramAuth, TELEGRAM_POLL_INTERVAL_MS, TELEGRAM_POLL_TIMEOUT_MS } from '@/lib/api';
import { useLanguage } from '@/contexts/LanguageContext';

const POLL_INTERVAL = TELEGRAM_POLL_INTERVAL_MS;
const POLL_TIMEOUT = TELEGRAM_POLL_TIMEOUT_MS;

export default function LoginPage() {
  const router = useRouter();
  const { user, loading: authLoading, login } = useAuth();
  const { t } = useLanguage();
  const [method, setMethod] = useState<'password' | 'telegram'>('password');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tgWaiting, setTgWaiting] = useState(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const getNext = () => {
    if (typeof window === 'undefined') return '/profile';
    const params = new URLSearchParams(window.location.search);
    return params.get('next') || '/profile';
  };

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    setTgWaiting(false);
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  const startPolling = useCallback(
    (state: string) => {
      stopPolling();
      setTgWaiting(true);
      let elapsed = 0;
      pollIntervalRef.current = setInterval(async () => {
        try {
          const res = await pollTelegramAuth(state);
          if (res.status === 'completed') {
            stopPolling();
            await login();
            router.replace(getNext());
          }
        } catch {
          // ignore poll errors
        }
        elapsed += POLL_INTERVAL;
        if (elapsed >= POLL_TIMEOUT) {
          stopPolling();
          setError(t('texts.login_timeout'));
        }
      }, POLL_INTERVAL);

      pollTimeoutRef.current = setTimeout(() => {
        stopPolling();
      }, POLL_TIMEOUT);
    },
    [stopPolling, login, router, t]
  );

  const handleTelegramLogin = async () => {
    setError('');
    setLoading(true);

    try {
      const res = await startTelegramAuth();
      const botUrl = res.url;
      const state = res.state;
      if (!botUrl || !state) {
        setError(t('texts.login_error'));
        setLoading(false);
        return;
      }
      const next = getNext();
      if (next && next !== '/profile') {
        try {
          sessionStorage.setItem(`vpn_auth_next_${state}`, next);
        } catch {
          // ignore
        }
      }
      window.open(botUrl, '_blank');
      setLoading(false);
      startPolling(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.login_error'));
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading && user) {
      router.replace(getNext());
    }
  }, [authLoading, user, router]);

  const redirectAfterLogin = () => {
    const next = getNext();
    router.replace(next);
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const session = await loginUser({ username, password });
      if (session) {
        await login();
        redirectAfterLogin();
      } else {
        setError(t('texts.login_error'));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.login_error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Header currentPage="/login" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.login_title')}</h1>
              <p className="profile-username">{t('texts.login_subtitle')}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div className="flex flex-col gap-4 mt-5">
                <div className="flex gap-2 mb-2">
                  <button
                    onClick={() => setMethod('password')}
                    className={
                      'flex-1 px-3 py-3.5 rounded-md text-sm cursor-pointer border transition-colors ' +
                      (method === 'password'
                        ? 'bg-[var(--accent-glow)] border-[var(--accent)] text-[var(--text-primary)]'
                        : 'border-[var(--border-color)] text-[var(--text-primary)] bg-transparent')
                    }
                  >
                    {t('buttons.password_login')}
                  </button>
                  <button
                    onClick={() => setMethod('telegram')}
                    className={
                      'flex-1 px-3 py-3.5 rounded-md text-sm cursor-pointer border transition-colors ' +
                      (method === 'telegram'
                        ? 'bg-[var(--accent-glow)] border-[var(--accent)] text-[var(--text-primary)]'
                        : 'border-[var(--border-color)] text-[var(--text-primary)] bg-transparent')
                    }
                  >
                    {t('buttons.telegram_login')}
                  </button>
                </div>

                {error && <div className="error-message">{error}</div>}

                {method === 'password' ? (
                  <form onSubmit={handlePasswordLogin} className="flex flex-col gap-3">
                    <input
                      type="text"
                      placeholder={t('texts.username')}
                      className="faq-search-input"
                      value={username}
                      onChange={(e) => setUsername(e.target.value.replace(/[<>"'&]/g, ''))}
                      required
                    />
                    <input
                      type="password"
                      placeholder={t('texts.password')}
                      className="faq-search-input"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                    <button type="submit" className="button w-full" disabled={loading}>
                      {loading ? t('texts.waiting') : t('texts.login_link')}
                    </button>
                  </form>
                ) : (
                  <div className="flex flex-col gap-3">
                    <button
                      onClick={handleTelegramLogin}
                      className="button"
                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', textDecoration: 'none' }}
                    >
                      <svg width="20" height="20" fill="currentColor" viewBox="0 0 30 30">
                        <path d="m20.665 3.717-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l.002.001-.314 4.692c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.434z" />
                      </svg>
                      {t('buttons.telegram_login')}
                    </button>
                    {tgWaiting && (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '8px',
                          padding: '12px',
                          background: 'rgba(59, 130, 246, 0.1)',
                          border: '1px solid rgba(59, 130, 246, 0.3)',
                          borderRadius: 'var(--radius-sm)',
                          color: 'var(--text-primary)',
                          fontSize: '14px',
                        }}
                      >
                        <div
                          style={{
                            width: '16px',
                            height: '16px',
                            border: '2px solid var(--border-color)',
                            borderTopColor: 'var(--accent)',
                            borderRadius: '50%',
                            animation: 'spin 0.8s linear infinite',
                          }}
                        />
                        {t('texts.telegram_waiting')}
                      </div>
                    )}
                    <p className="text-center text-secondary text-sm">
                      {t('texts.telegram_login_hint')}
                    </p>
                  </div>
                )}

                <p className="text-center text-secondary text-sm">
                  {t('texts.no_account')}{' '}
                  <Link href="/register" className="font-semibold">
                    {t('texts.register_link')}
                  </Link>
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

