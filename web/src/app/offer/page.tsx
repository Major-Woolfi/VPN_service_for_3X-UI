import { cookies, headers } from 'next/headers';
import Header from '@/components/Header';
import { tServer, resolveLanguage } from '@/lib/i18n-server';
import { getSiteCopy } from '@/data/legal';

export default async function OfferPage() {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolveLanguage(
    cookieStore.get('vpn_language')?.value,
    headerStore.get('accept-language') || undefined,
  );
  const t = (key: string, params?: Record<string, string | number>) => tServer(lang, key, params);
  const copy = getSiteCopy(lang);

  return (
    <>
      <Header currentPage="/offer" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{copy.legal.offer.title}</h1>
              <p className="profile-username">{copy.legal.offer.subtitle}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div style={{ marginTop: '16px', lineHeight: '1.6' }}>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
                  <strong>{t('texts.effective_date', { date: copy.legal.offer.effectiveDate })}</strong>
                </p>
                {copy.legal.offer.sections.map((section, idx) => (
                  <div key={idx}>
                    <h2 style={{ marginTop: idx === 0 ? '0' : '24px' }}>{section.title}</h2>
                    <p
                      style={{ color: 'var(--text-secondary)' }}
                      dangerouslySetInnerHTML={{ __html: section.content }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

