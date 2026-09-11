'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { useNavigation } from '@/lib/navigation';
import { getAvailableLanguages, getLanguageDisplayName, setCurrentLang } from '@/lib/i18n';
import { changeLanguage } from '@/lib/api';

function LanguageSwitcher() {
  const { user, refreshUser } = useAuth();
  const [langOpen, setLangOpen] = useState(false);
  const { lang } = useLanguage();
  const router = useRouter();
  const isAdmin = Boolean(user?.is_admin);

  const handleSelect = async (code: string) => {
    setLangOpen(false);
    if (!user) {
      setCurrentLang(code);
      router.refresh();
      return;
    }
    try {
      await changeLanguage(code);
      setCurrentLang(code);
      await refreshUser();
      router.refresh();
    } catch {
      setCurrentLang(code);
      router.refresh();
    }
  };

  return (
    <div className={`user-menu-language ${langOpen ? 'open' : ''}`}>
      <button
        type="button"
        className="user-menu-link user-menu-lang-trigger"
        aria-expanded={langOpen}
        onClick={() => setLangOpen((v) => !v)}
      >
        {getLanguageDisplayName(lang)} ({lang.toUpperCase()})
      </button>
      <div className="user-menu-lang-wrapper">
        <div className="user-menu-lang-collapse">
          <div className="user-menu-lang-inner">
            {getAvailableLanguages().map((code) => (
              <button
                type="button"
                key={code}
                className={`user-menu-link user-menu-lang-btn ${lang === code ? 'nav-lang-active' : ''}`}
                onClick={() => handleSelect(code)}
              >
                {getLanguageDisplayName(code)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function UserMenu() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { authorizedLinks } = useNavigation();
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const initial = user?.username?.charAt(0).toUpperCase() || '?';

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const handleLogout = async () => {
    await logout();
    setOpen(false);
    router.push('/');
    router.refresh();
  };

  const isPartner = Boolean(user?.is_partner && !user?.is_admin);

  return (
    <div ref={menuRef} className="user-menu">
      <button
        type="button"
        className="avatar-button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={user ? t('texts.menu_profile_label', { username: user.username || user.user_id }) : t('texts.menu_login_label')}
      >
        <span className="avatar-placeholder" aria-hidden="true">{initial}</span>
        <svg className="avatar-caret" aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M4 4l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="user-menu-popover" role="menu">
          {user ? (
            <>
              <div className="user-menu-summary">
                <strong>{user.username || `ID:${user.user_id}`}</strong>
                <span>{t('texts.user_id')}: {user.user_id}</span>
              </div>
              {authorizedLinks.map((link) => (
                <Link key={link.href} href={link.href} className="user-menu-link" onClick={() => setOpen(false)}>
                  {link.label}
                </Link>
              ))}
              <LanguageSwitcher />
              <button type="button" className="user-menu-link user-menu-action" onClick={toggleTheme}>
                {theme === 'dark' ? t('buttons.light_theme') : t('buttons.dark_theme')}
              </button>
              {isPartner && (
                <>
                  <div className="user-menu-divider" />
                  <div className="user-menu-section-header">{t('texts.partners_section')}</div>
                  <Link href="/partner" className="user-menu-link" onClick={() => setOpen(false)}>
                    {t('buttons.partner')}
                  </Link>
                </>
              )}
              {user.is_admin && (
                <Link href="/admin/health" className="user-menu-link" onClick={() => setOpen(false)}>
                  {t('texts.admin_panel')}
                </Link>
              )}
              <button type="button" className="user-menu-link user-menu-danger" onClick={handleLogout}>
                {t('buttons.logout')}
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="user-menu-link" onClick={() => setOpen(false)}>
                {t('buttons.login')}
              </Link>
              <Link href="/register" className="user-menu-link" onClick={() => setOpen(false)}>
                {t('buttons.register')}
              </Link>
              <LanguageSwitcher />
              <button type="button" className="user-menu-link user-menu-action" onClick={toggleTheme}>
                {theme === 'dark' ? t('buttons.light_theme') : t('buttons.dark_theme')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

