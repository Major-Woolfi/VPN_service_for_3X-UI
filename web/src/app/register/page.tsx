'use client';

import Header from '@/components/Header';
import Link from 'next/link';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { registerUser } from '@/lib/api';
import { useLanguage } from '@/contexts/LanguageContext';

export default function RegisterPage() {
  const router = useRouter();
  const { user, login, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!authLoading && user) {
      router.replace('/profile');
    }
  }, [authLoading, user, router]);

  const handlePasswordRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Sanitize username: remove potential XSS characters
    const sanitizedUsername = username.replace(/[<>"'&]/g, '').trim();
    if (sanitizedUsername.length < 3) {
      setError(t('texts.username_too_short'));
      return;
    }
    if (password.length < 10) {
      setError(t('texts.password_too_short'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('texts.passwords_mismatch'));
      return;
    }

    setLoading(true);

    try {
      const session = await registerUser({ username: sanitizedUsername, password });
      if (session) {
        const userData = await login();
        if (userData) {
          router.push('/profile');
        } else {
          setError(t('texts.login_failed_after_register'));
        }
      } else {
        setError(t('texts.register_error'));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.register_error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Header currentPage="/register" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.register_title')}</h1>
              <p className="profile-username">{t('texts.register_subtitle')}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div className="flex flex-col gap-4 mt-5">
                {error && <div className="error-message">{error}</div>}

                <form onSubmit={handlePasswordRegister} className="flex flex-col gap-3">
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
                  <input
                    type="password"
                    placeholder={t('texts.confirm_password')}
                    className="faq-search-input"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                  />
                  <button type="submit" className="button w-full" disabled={loading}>
                    {loading ? t('texts.waiting') : t('texts.register_link')}
                  </button>
                </form>

                <p className="text-center text-secondary text-sm">
                  {t('texts.have_account')}{' '}
                  <Link href="/login" className="font-semibold">
                    {t('texts.login_link')}
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

