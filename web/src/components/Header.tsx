'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import UserMenu from './UserMenu';
import { useLanguage } from '@/contexts/LanguageContext';
import { useNavigation } from '@/lib/navigation';

export default function Header({ currentPage = '' }: { currentPage?: string }) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const { t } = useLanguage();
  const { publicLinks, authorizedLinks, adminLinks, contactLinks } = useNavigation();

  useEffect(() => {
    const handler = () => {
      router.refresh();
    };
    window.addEventListener('vpn-languagechange', handler);
    return () => window.removeEventListener('vpn-languagechange', handler);
  }, [router]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <>
      <header className="github-nav">
        <div className="nav-left">
          <button
            id="nav-logo"
            className="nav-logo"
            type="button"
            aria-expanded={menuOpen}
            aria-label={t('texts.nav_open_menu')}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="hamburger" aria-hidden="true"><span /><span /><span /></span>
          </button>
        </div>
        <nav className="nav-middle" aria-label={t('texts.nav_main_navigation')}>
          {publicLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`nav-link ${currentPage === link.href ? 'nav-link-active' : ''}`}
              aria-current={currentPage === link.href ? 'page' : undefined}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="nav-right">
          <UserMenu />
        </div>
      </header>

      <aside id="site-navigation" className={`side-nav ${menuOpen ? 'open' : ''}`} aria-label="Navigation">
        <div className="side-nav-header">
          <strong>{process.env.NEXT_PUBLIC_VPN_NAME || 'VPN'}</strong>
          <button type="button" className="side-nav-close" onClick={() => setMenuOpen(false)} aria-label={t('texts.nav_close_menu')}>×</button>
        </div>
        <ul>
          <li className="nav-section-header">{t('texts.public_section')}</li>
          {publicLinks.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className={currentPage === link.href ? 'nav-link-active' : ''}
                aria-current={currentPage === link.href ? 'page' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </Link>
            </li>
          ))}
          <li className="nav-divider" aria-hidden="true" />
          <li className="nav-section-header">{t('texts.authorized_section')}</li>
          {authorizedLinks.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className={currentPage === link.href ? 'nav-link-active' : ''}
                aria-current={currentPage === link.href ? 'page' : undefined}
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </Link>
            </li>
          ))}
          <li className="nav-divider" aria-hidden="true" />
          {adminLinks.length > 0 && (
            <>
              <li className="nav-section-header">{t('texts.admin_section')}</li>
              {adminLinks.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className={currentPage === link.href ? 'nav-link-active' : ''}
                    aria-current={currentPage === link.href ? 'page' : undefined}
                    onClick={() => setMenuOpen(false)}
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
              <li className="nav-divider" aria-hidden="true" />
            </>
          )}
          {contactLinks.length > 0 && (
            <>
              <li className="nav-section-header">{t('texts.contact_section')}</li>
              {contactLinks.map((social) => (
                <li key={social.href}>
                  <a
                    href={social.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setMenuOpen(false)}
                  >
                    {social.label}
                  </a>
                </li>
              ))}
            </>
          )}
        </ul>
      </aside>

      <button
        id="nav-overlay"
        className={`overlay ${menuOpen ? 'open' : ''}`}
        aria-label={t('texts.nav_close_menu')}
        onClick={() => setMenuOpen(false)}
      />
    </>
  );
}

