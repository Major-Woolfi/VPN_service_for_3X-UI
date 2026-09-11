'use client';

import Header from '@/components/Header';
import Link from 'next/link';
import { useLanguage } from '@/contexts/LanguageContext';

export default function NotFound() {
  const { t } = useLanguage();
  return (
    <>
      <Header currentPage="" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.not_found')}</h1>
            </div>
          </div>
          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
                {t('texts.not_found_text')}
              </p>
              <Link href="/" className="button">
                {t('buttons.main')}
              </Link>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

