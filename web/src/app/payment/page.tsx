'use client';

import Header from '@/components/Header';
import { useFeatures } from '@/contexts/FeaturesContext';
import { useLanguage } from '@/contexts/LanguageContext';

export default function PaymentPage() {
  const { features, loading } = useFeatures();
  const { t } = useLanguage();

  const paymentMethods = features?.payment_methods || [];
  const cardNumber = features?.payment_card || '';
  const yoomoney = features?.yoomoney || '';

  if (loading) {
    return (
      <>
        <Header currentPage="/payment" />
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

  return (
    <>
      <Header currentPage="/payment" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('texts.payment_title')}</h1>
              <p className="profile-username">{t('texts.payment_subtitle')}</p>
            </div>
          </div>

          {paymentMethods.length === 0 ? (
            <div className="pinned-section fade-in">
              <div className="pinned-content">
                <p style={{ color: 'var(--text-secondary)', textAlign: 'center', marginTop: '16px' }}>
                  {t('texts.no_payment_methods')}
                </p>
              </div>
            </div>
          ) : (
            <div className="pinned-section fade-in">
              <h2>{t('texts.payment_methods')}</h2>
              <div className="pinned-content">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
                    gap: '16px',
                    marginTop: '16px',
                  }}
                >
                  {paymentMethods.includes('yoomoney') && (
                    <div
                      style={{
                        padding: '20px',
                        background: 'var(--bg-tertiary)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <h3 style={{ margin: '0 0 12px' }}>{t('texts.yoomoney')}</h3>
                      <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                        {t('texts.yoomoney_text')}
                      </p>
                      <div
                        style={{
                          marginTop: '12px',
                          padding: '12px',
                          background: 'var(--bg-primary)',
                          borderRadius: 'var(--radius-sm)',
                          fontFamily: 'monospace',
                          fontSize: '14px',
                        }}
                      >
                        {yoomoney}
                      </div>
                    </div>
                  )}

                  {paymentMethods.includes('card') && (
                    <div
                      style={{
                        padding: '20px',
                        background: 'var(--bg-tertiary)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <h3 style={{ margin: '0 0 12px' }}>{t('texts.p2p')}</h3>
                      <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                        {t('texts.p2p_text')}
                      </p>
                      <div
                        style={{
                          marginTop: '12px',
                          padding: '12px',
                          background: 'var(--bg-primary)',
                          borderRadius: 'var(--radius-sm)',
                          fontFamily: 'monospace',
                          fontSize: '14px',
                        }}
                      >
                        {cardNumber}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="pinned-section fade-in delay-1">
            <h2>{t('texts.payment_order')}</h2>
            <div className="pinned-content">
              <ol style={{ marginTop: '16px', paddingLeft: '20px' }}>
                <li style={{ marginBottom: '12px' }}>{t('texts.step_1')}</li>
                <li style={{ marginBottom: '12px' }}>{t('texts.step_2')}</li>
                <li style={{ marginBottom: '12px' }}>{t('texts.step_3')}</li>
                <li>{t('texts.step_4')}</li>
              </ol>
            </div>
          </div>

          <div className="pinned-section fade-in delay-2">
            <h2>{t('texts.refund')}</h2>
            <div className="pinned-content">
              <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>
                {t('texts.refund_text')}
              </p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

