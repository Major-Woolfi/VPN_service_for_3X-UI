'use client';

import Header from '@/components/Header';
import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/contexts/LanguageContext';
import { useFeatures } from '@/contexts/FeaturesContext';
import { getTariffs, createCheckout, generateCustomTariff, getLocations, trialSubscription, getCustomTariffParams } from '@/lib/api';
import type { Tariff, Location, CustomTariffParams } from '@/lib/types';
import TariffGrid from '@/components/TariffGrid';

type Step = 'select' | 'offer' | 'payment' | 'custom';

export default function SubscribePage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { t, tHtml } = useLanguage();
  const { features, loading: featuresLoading } = useFeatures();
  const [tariffs, setTariffs] = useState<Tariff[]>([]);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState<Step>('select');
  const [selectedTariff, setSelectedTariff] = useState<Tariff | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<'card' | 'yoomoney'>('card');
  const [error, setError] = useState('');
  const [processing, setProcessing] = useState(false);
  const [checkoutResult, setCheckoutResult] = useState<{
    checkout_url: string;
    payment_id: string;
    auto_confirmed?: boolean;
    vpn_url?: string;
  } | null>(null);
  const [hasPendingPartnerApplication, setHasPendingPartnerApplication] = useState(false);
  const [isPartner, setIsPartner] = useState(false);
  const [userSubscriptionStatus, setUserSubscriptionStatus] = useState('');
  const [trialUsed, setTrialUsed] = useState(false);
  const [hasPendingPayment, setHasPendingPayment] = useState(false);
  const [trialDone, setTrialDone] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [telegramLinked, setTelegramLinked] = useState(false);
  const [customTraffic, setCustomTraffic] = useState(10);
  const [customIp, setCustomIp] = useState(1);
  const [customDays, setCustomDays] = useState(30);
  const [customPrice, setCustomPrice] = useState<number | null>(null);
  const [customPriceLoading, setCustomPriceLoading] = useState(false);
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [locations, setLocations] = useState<Location[]>([]);
  const [selectedLocations, setSelectedLocations] = useState<string[]>([]);
  const [customTariffParams, setCustomTariffParams] = useState<CustomTariffParams | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [tariffs, locations, customParams] = await Promise.all([
          getTariffs(),
          getLocations(),
          features?.features?.custom_tariff && user ? getCustomTariffParams() : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setTariffs(tariffs);
          setLocations(locations);
          setCustomTariffParams(customParams);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to load tariffs:', err);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user, features?.features?.custom_tariff]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace('/login?next=/subscribe');
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsPartner(user.is_partner);
    setHasPendingPartnerApplication(user.pending_partner_application);
    setUserSubscriptionStatus(user.subscription.status);
    setTrialUsed(Boolean(user.trial_used));
    setHasPendingPayment(Boolean(user.has_pending_payment));
    setIsAdmin(Boolean(user.is_admin));
    setTelegramLinked(user.telegram_id > 0);
    setLoading(false);
  }, [authLoading, user, router]);

  const isSubscribed = userSubscriptionStatus === 'active';
  const eligibleForTrial = !trialUsed && !isSubscribed && !isAdmin;
  const canBuy = !isSubscribed && !hasPendingPayment;
  const visibleTariffs = useMemo(
    () => tariffs.filter((t) => t.active && (!t.is_trial || eligibleForTrial)),
    [tariffs, eligibleForTrial]
  );

  const handleSelectTariff = (tariff: Tariff) => {
    if (hasPendingPartnerApplication) {
      setError(t('texts.partner_application_pending_block'));
      return;
    }
    if (!canBuy) {
      setError(t('texts.purchase_blocked_wait_admin'));
      return;
    }
    if (tariff.is_trial && !telegramLinked) {
      setError(t('texts.trial_requires_telegram'));
      return;
    }
    setSelectedTariff(tariff);
    setStep('offer');
    setError('');
  };

  const handleAcceptOffer = async () => {
    if (!selectedTariff) return;
    if (selectedTariff.is_trial) {
      await handleTrial();
      return;
    }
    setStep('payment');
    setError('');
  };

  const handleTrial = async () => {
    setProcessing(true);
    setError('');
    try {
      await trialSubscription();
      setTrialDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.checkout_error'));
    } finally {
      setProcessing(false);
    }
  };

  const handlePay = async () => {
    if (!user || !selectedTariff) return;
    setProcessing(true);
    setError('');

    if (isPartner && userSubscriptionStatus === 'active') {
      setError(t('texts.active_partner_subscription_guard'));
      setProcessing(false);
      return;
    }

    try {
      const result = await createCheckout({
        plan_id: selectedTariff.id,
        method: paymentMethod === 'yoomoney' ? 'yoomoney' : 'manual',
      });
      setCheckoutResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.checkout_error'));
    } finally {
      setProcessing(false);
    }
  };

  const handleCustomTariffChange = async () => {
    if (!user || customPriceLoading) return;
    if (selectedLocations.length < 1) {
      setError(t('texts.custom_tariff_no_locations'));
      return;
    }
    try {
      setCustomPriceLoading(true);
      const result = await generateCustomTariff({
        traffic_gb: customTraffic,
        ip_limit: customIp,
        duration_days: customDays,
        servers: selectedLocations,
      });
      setCustomPrice(result.total_price);
    } catch {
      setCustomPrice(null);
    } finally {
      setCustomPriceLoading(false);
    }
  };

  const handleSelectCustomTariff = () => {
    if (hasPendingPartnerApplication) {
      setError(t('texts.partner_application_pending_block'));
      return;
    }
    if (!canBuy) {
      setError(t('texts.purchase_blocked_wait_admin'));
      return;
    }
    if (selectedLocations.length < 1) {
      setError(t('texts.custom_tariff_no_locations'));
      return;
    }
    if (customPrice === null) {
      setError(t('texts.custom_tariff_error'));
      return;
    }
    const customTariff: Tariff = {
      id: 'custom',
      name: `${t('texts.custom_tariff')} ${customTraffic}GB / ${customIp}IP / ${customDays}d`,
      price_rub: customPrice,
      traffic_gb: customTraffic,
      ip_limit: customIp,
      duration_days: customDays,
      servers: selectedLocations,
      active: true,
      locations: selectedLocations,
    };
    setSelectedTariff(customTariff);
    setStep('offer');
    setError('');
  };

  const handlePayCustom = async () => {
    if (!user || !selectedTariff) return;
    setProcessing(true);
    setError('');

    if (isPartner && userSubscriptionStatus === 'active') {
      setError(t('texts.active_partner_subscription_guard'));
      setProcessing(false);
      return;
    }

    try {
      const result = await createCheckout({
        plan_id: 'custom',
        method: paymentMethod === 'yoomoney' ? 'yoomoney' : 'manual',
        custom_plan: {
          name: selectedTariff.name,
          price_rub: selectedTariff.price_rub,
          ip_limit: selectedTariff.ip_limit,
          traffic_gb: selectedTariff.traffic_gb,
          duration_days: selectedTariff.duration_days,
          servers: selectedTariff.servers,
        },
      });
      setCheckoutResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('texts.checkout_error'));
    } finally {
      setProcessing(false);
    }
  };

  const availableMethods = features?.payment_methods || [];
  const cardNumber = features?.payment_card || '';
  const yoomoneyWallet = features?.yoomoney || '';

  const [yooOrderId] = useState(() => `web_${Date.now()}`);

  const yooUrl = useMemo(() => {
    if (!yoomoneyWallet || !selectedTariff) return '';
    const params = new URLSearchParams({
      receiver: yoomoneyWallet,
      'quickpay-form': 'shop',
      targets: `VPN #${yooOrderId}`,
      paymentType: 'AC',
      sum: String(selectedTariff.price_rub),
      label: yooOrderId,
    });
    return `https://yoomoney.ru/quickpay/confirm?${params.toString()}`;
  }, [yoomoneyWallet, selectedTariff, yooOrderId]);

  useEffect(() => {
    if ((checkoutResult || trialDone) && !processing) {
      const timer = setTimeout(() => {
        router.push('/profile');
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [checkoutResult, processing, router, trialDone]);

  if (authLoading || featuresLoading || loading || !user) {
    return (
      <>
        <Header currentPage="/subscribe" />
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

  if (availableMethods.length === 0) {
    return (
      <>
        <Header currentPage="/subscribe" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t('buttons.buy')}</h1>
                <p className="profile-username">{t('texts.tariffs')}</p>
              </div>
            </div>
            {visibleTariffs.length > 0 ? (
              <div className="pinned-section fade-in">
                <h2>{t('texts.tariffs')}</h2>
                <div className="pinned-content">
                  {!canBuy && (
                    <div
                      className="card"
                      style={{
                        marginBottom: '16px',
                        background: 'var(--accent-glow)',
                        border: '1px solid var(--accent)',
                        color: 'var(--text-primary)',
                        fontSize: '14px',
                        lineHeight: '1.5',
                      }}
                    >
                      {t('texts.purchase_blocked_wait_admin')}
                    </div>
                  )}
                  <TariffGrid
                    tariffs={visibleTariffs}
                    onSelect={handleSelectTariff}
                  />
                  <div
                    className="card"
                    style={{
                      marginTop: '16px',
                      background: 'var(--accent-glow)',
                      border: '1px solid var(--accent)',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      lineHeight: '1.5',
                    }}
                  >
                    {t('texts.no_payment_methods')}
                  </div>
                </div>
              </div>
            ) : (
              <div className="pinned-section fade-in">
                <div className="pinned-content">
                  <p style={{ color: 'var(--text-secondary)', textAlign: 'center', marginTop: '16px' }}>
                    {t('texts.no_tariffs_available')}
                  </p>
                </div>
              </div>
            )}
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Header currentPage="/subscribe" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t('buttons.buy')}</h1>
              <p className="profile-username">
                {step === 'select' && t('texts.tariffs')}
                {step === 'offer' && t('texts.public_offer')}
                {step === 'payment' && t('texts.payment_title')}
              </p>
            </div>
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          {step === 'select' && (
            <div className="pinned-section fade-in">
              <h2>{t('texts.tariffs')}</h2>
              <div className="pinned-content">
                {!canBuy && (
                  <div
                    className="card"
                    style={{
                      marginBottom: '16px',
                      background: 'var(--accent-glow)',
                      border: '1px solid var(--accent)',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      lineHeight: '1.5',
                    }}
                  >
                    {t('texts.purchase_blocked_wait_admin')}
                  </div>
                )}
                {isAdmin && (
                  <div
                    className="card"
                    style={{
                      marginBottom: '16px',
                      background: 'var(--accent-glow)',
                      border: '1px solid var(--accent)',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      lineHeight: '1.5',
                    }}
                  >
                    {t('texts.trial_admin_only_bot')}
                  </div>
                )}
                {eligibleForTrial && !telegramLinked && (
                  <div
                    className="card"
                    style={{
                      marginBottom: '16px',
                      background: 'var(--accent-glow)',
                      border: '1px solid var(--accent)',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      lineHeight: '1.5',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                    }}
                  >
                    <span>{t('texts.trial_requires_telegram')}</span>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => router.push('/settings')}
                    >
                      {t('buttons.link_telegram')}
                    </button>
                  </div>
                )}
                {visibleTariffs.length === 0 ? (
                  <p style={{ color: 'var(--text-secondary)' }}>{t('texts.no_tariffs_available')}</p>
                ) : (
                  <TariffGrid
                    tariffs={visibleTariffs}
                    onSelect={handleSelectTariff}
                  />
                )}
              </div>
            </div>
          )}

          {step === 'select' && features?.features?.custom_tariff && (
            <div className="pinned-section fade-in delay-1">
              <h2>{t('texts.custom_tariff')}</h2>
              <div className="pinned-content">
                <div className="card" style={{ marginTop: '16px', background: 'var(--accent-glow)', border: '1px solid var(--accent)' }}>
                  <p className="text-secondary" style={{ fontSize: '13px', lineHeight: '1.5', marginBottom: '8px' }}>
                    {t('texts.custom_tariff_description', {
                      min_gb: customTariffParams?.min_gb || 1,
                      max_gb: customTariffParams?.max_gb || 1000,
                      min_ip: customTariffParams?.min_ip || 1,
                      max_ip: customTariffParams?.max_ip || 10,
                      min_days: customTariffParams?.min_days || 1,
                      max_days: customTariffParams?.max_days || 365,
                    })}
                  </p>
                  {customTariffParams && (
                    <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
                      <div
                        style={{
                          padding: '10px',
                          background: 'var(--bg-primary)',
                          borderRadius: 'var(--radius-sm)',
                          fontFamily: 'monospace',
                          fontSize: '12px',
                          lineHeight: '1.4',
                          marginBottom: '12px',
                          textAlign: 'center',
                        }}
                        dangerouslySetInnerHTML={{
                          __html: t('texts.custom_tariff_formula'),
                        }}
                      />
                      <p style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '6px' }}>
                        {t('texts.custom_tariff_formula_params')}
                      </p>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                        <div dangerouslySetInnerHTML={{ __html: t('texts.custom_tariff_param_gb') }} />
                        <div dangerouslySetInnerHTML={{ __html: t('texts.custom_tariff_param_ip') }} />
                        <div dangerouslySetInnerHTML={{ __html: t('texts.custom_tariff_param_days') }} />
                        <div style={{ marginTop: '4px' }} dangerouslySetInnerHTML={{ __html: t('texts.custom_tariff_param_locations') }} />
                        {customTariffParams.locations.length > 0 ? (
                          <div style={{ marginLeft: '12px', marginTop: '2px' }}>
                            {customTariffParams.locations.map((loc) => (
                              <div key={loc.code} dangerouslySetInnerHTML={{
                                __html: t('texts.custom_tariff_location_price_line', {
                                  label: loc.label || loc.code.toUpperCase(),
                                  price: loc.price_per_day_rub || 0,
                                }),
                              }} />
                            ))}
                          </div>
                        ) : (
                          <div style={{ marginLeft: '12px', marginTop: '2px' }} dangerouslySetInnerHTML={{ __html: t('texts.custom_tariff_no_locations') }} />
                        )}
                      </div>
                      <div style={{ marginTop: '12px', paddingTop: '8px', borderTop: '1px solid var(--border-color)', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        base = {customTariffParams.base_price} ₽ · gb_coef = {customTariffParams.gb_coef} ₽ · ip_day_coef = {customTariffParams.ip_day_coef} ₽
                      </div>
                    </div>
                  )}
                </div>
                {!showCustomForm ? (
                  <button
                    onClick={() => setShowCustomForm(true)}
                    className="button"
                    style={{ width: '100%', marginTop: '16px' }}
                  >
                    {t('texts.custom_tariff_collect')}
                  </button>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                      <div style={{ flex: 1, minWidth: '120px' }}>
                        <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', display: 'block' }}>
                          {t('texts.traffic')}
                        </label>
                          <div className="number-input-wrapper">
                          <button type="button" className="number-btn" onClick={() => { setCustomTraffic(Math.max(customTariffParams?.min_gb || 1, customTraffic - 1)); setCustomPrice(null); }}>-</button>
                          <input
                            type="number"
                            min={customTariffParams?.min_gb || 1}
                            max={customTariffParams?.max_gb || 1000}
                            value={customTraffic}
                            onChange={(e) => {
                              setCustomTraffic(parseInt(e.target.value) || 1);
                              setCustomPrice(null);
                            }}
                          />
                          <button type="button" className="number-btn" onClick={() => { setCustomTraffic(Math.min(customTariffParams?.max_gb || 1000, customTraffic + 1)); setCustomPrice(null); }}>+</button>
                        </div>
                      </div>
                      <div style={{ flex: 1, minWidth: '120px' }}>
                        <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', display: 'block' }}>
                          {t('texts.ips')}
                        </label>
                        <div className="number-input-wrapper">
                          <button type="button" className="number-btn" onClick={() => { setCustomIp(Math.max(customTariffParams?.min_ip || 1, customIp - 1)); setCustomPrice(null); }}>-</button>
                          <input
                            type="number"
                            min={customTariffParams?.min_ip || 1}
                            max={customTariffParams?.max_ip || 15}
                            value={customIp}
                            onChange={(e) => {
                              setCustomIp(parseInt(e.target.value) || 1);
                              setCustomPrice(null);
                            }}
                          />
                          <button type="button" className="number-btn" onClick={() => { setCustomIp(Math.min(customTariffParams?.max_ip || 15, customIp + 1)); setCustomPrice(null); }}>+</button>
                        </div>
                      </div>
                      <div style={{ flex: 1, minWidth: '120px' }}>
                        <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', display: 'block' }}>
                          {t('texts.days')}
                        </label>
                        <div className="number-input-wrapper">
                          <button type="button" className="number-btn" onClick={() => { setCustomDays(Math.max(customTariffParams?.min_days || 1, customDays - 1)); setCustomPrice(null); }}>-</button>
                          <input
                            type="number"
                            min={customTariffParams?.min_days || 1}
                            max={customTariffParams?.max_days || 365}
                            value={customDays}
                            onChange={(e) => {
                              setCustomDays(parseInt(e.target.value) || 1);
                              setCustomPrice(null);
                            }}
                          />
                          <button type="button" className="number-btn" onClick={() => { setCustomDays(Math.min(customTariffParams?.max_days || 365, customDays + 1)); setCustomPrice(null); }}>+</button>
                        </div>
                      </div>
                      </div>
                      {locations.length > 0 && (
                        <div>
                          <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px', display: 'block' }}>
                            {t('texts.locations')}
                          </label>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {locations.map((loc) => {
                              const isSelected = selectedLocations.includes(loc.code);
                              return (
                                <button
                                  key={loc.code}
                                  type="button"
                                  onClick={() => {
                                    setSelectedLocations(prev =>
                                      isSelected
                                        ? prev.filter(c => c !== loc.code)
                                        : [...prev, loc.code]
                                    );
                                    setCustomPrice(null);
                                  }}
                                  className="card"
                                  style={{
                                    padding: '8px 12px',
                                    fontSize: '13px',
                                    cursor: 'pointer',
                                    background: isSelected ? 'var(--accent-glow)' : undefined,
                                    border: isSelected ? '1px solid var(--accent)' : undefined,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '6px',
                                  }}
                                >
                                  <span>{loc.flag}</span>
                                  <span>{loc.code.toUpperCase()}</span>
                                  {loc.price_per_day_rub && (
                                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                                       +{loc.price_per_day_rub}₽{t('texts.per_day_short')}
                                    </span>
                                  )}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      {customPrice !== null && (
                      <div style={{ padding: '12px', background: 'var(--accent-glow)', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>
                        <span style={{ fontSize: '18px', fontWeight: '700', color: 'var(--accent)' }}>
                          {customPrice} ₽
                        </span>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => { setShowCustomForm(false); setCustomPrice(null); }}
                        className="button"
                        style={{ flex: 1, background: 'var(--bg-tertiary)' }}
                      >
                        {t('buttons.cancel')}
                      </button>
                      <button
                        onClick={handleCustomTariffChange}
                        className="button"
                        style={{ flex: 1, background: 'var(--bg-tertiary)' }}
                        disabled={customPriceLoading}
                      >
                        {customPriceLoading ? t('texts.loading') : t('texts.calculate_price')}
                      </button>
                      <button
                        onClick={handleSelectCustomTariff}
                        className="button"
                        style={{ flex: 1 }}
                        disabled={customPrice === null || customPriceLoading}
                      >
                        {t('texts.select_custom_tariff')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 'offer' && selectedTariff && (
            <div className="pinned-section fade-in">
              <h2>{t('texts.public_offer')}</h2>
              <div className="pinned-content">
                <div className="mt-4">
                  <div className="card" style={{ marginBottom: '16px' }}>
                    <h3>{selectedTariff.name}</h3>
                    <p className="text-secondary" style={{ fontSize: '14px', marginTop: '8px' }}>
                      {selectedTariff.price_rub} ₽ ·{' '}
                      {t('texts.duration_days', { days: selectedTariff.duration_days })} ·{' '}
                      {t('texts.traffic_gb', { value: selectedTariff.traffic_gb })} ·{' '}
                      {selectedTariff.ip_limit} {t('texts.ips')}
                    </p>
                  </div>
                  <p className="text-secondary" style={{ fontSize: '14px', lineHeight: '1.6' }}>
                    {t('texts.offer_text_1')} {t('texts.offer_text_2')} {t('texts.offer_text_3')}
                  </p>
                  <blockquote className="mt-4">
                    {t('texts.offer_section_2')}: {t('texts.offer_text_2')}
                  </blockquote>
                  <div className="flex-center gap-3 mt-4">
                    <button
                      onClick={() => setStep('select')}
                      className="button"
                      style={{ flex: 1, background: 'var(--bg-tertiary)' }}
                    >
                      {t('buttons.cancel')}
                    </button>
                    <button onClick={handleAcceptOffer} className="button" style={{ flex: 1 }}>
                      {t('buttons.continue')}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {step === 'payment' && selectedTariff && availableMethods.length > 0 && (
            <div className="pinned-section fade-in">
              <h2>{t('texts.payment_title')}</h2>
              <div className="pinned-content">
                <div className="mt-4">
                  {availableMethods.length > 1 && (
                    <div className="flex-center gap-3" style={{ marginBottom: '24px' }}>
                      {availableMethods.includes('card') && (
                        <button
                          onClick={() => setPaymentMethod('card')}
                          className="card"
                          style={{
                            flex: 1,
                            background: paymentMethod === 'card' ? 'var(--accent-glow)' : undefined,
                            border: paymentMethod === 'card' ? '1px solid var(--accent)' : undefined,
                            textAlign: 'center',
                            color: 'var(--text-primary)',
                            cursor: 'pointer',
                          }}
                        >
                          <div style={{ fontWeight: '600', marginBottom: '4px' }}>{t('texts.p2p')}</div>
                          <div className="text-secondary" style={{ fontSize: '12px' }}>
                            {t('texts.p2p_text')}
                          </div>
                        </button>
                      )}
                      {availableMethods.includes('yoomoney') && (
                        <button
                          onClick={() => setPaymentMethod('yoomoney')}
                          className="card"
                          style={{
                            flex: 1,
                            background: paymentMethod === 'yoomoney' ? 'var(--accent-glow)' : undefined,
                            border: paymentMethod === 'yoomoney' ? '1px solid var(--accent)' : undefined,
                            textAlign: 'center',
                            color: 'var(--text-primary)',
                            cursor: 'pointer',
                          }}
                        >
                          <div style={{ fontWeight: '600', marginBottom: '4px' }}>
                            {t('texts.yoomoney')}
                          </div>
                          <div className="text-secondary" style={{ fontSize: '12px' }}>
                            {t('texts.yoomoney_text')}
                          </div>
                        </button>
                      )}
                    </div>
                  )}

                  <div className="card" style={{ marginBottom: '24px' }}>
                    <div className="mb-4">
                      <span className="text-secondary">{t('texts.plan')}: </span>
                      <span style={{ fontWeight: '600' }}>{selectedTariff.name}</span>
                    </div>
                    <div className="mb-4">
                      <span className="text-secondary">{t('texts.amount')}: </span>
                      <span style={{ fontWeight: '700', fontSize: '18px', color: 'var(--accent)' }}>
                        {selectedTariff.price_rub} ₽
                      </span>
                    </div>
                    {paymentMethod === 'yoomoney' ? (
                      <a
                        href={yooUrl || undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="button"
                        style={{ width: '100%', display: 'block', textAlign: 'center', textDecoration: 'none', marginBottom: '12px' }}
                      >
                        {t('texts.pay_now')}
                      </a>
                    ) : (
                      <div
                        className="card"
                        style={{
                          background: 'var(--bg-primary)',
                          fontFamily: 'monospace',
                          fontSize: '16px',
                          textAlign: 'center',
                          letterSpacing: '2px',
                          marginBottom: '12px',
                        }}
                      >
                        {cardNumber}
                      </div>
                    )}
                    <p className="text-secondary" style={{ fontSize: '13px', textAlign: 'center' }} dangerouslySetInnerHTML={{ __html: tHtml('texts.payment_instructions') }} />
                  </div>

                  {(checkoutResult || trialDone) && (
                    <div className="success-message" style={{ marginBottom: '24px' }}>
                      {trialDone ? (
                        <p style={{ fontWeight: '600', marginBottom: '8px' }}>
                          {t('texts.trial_activated')}
                        </p>
                      ) : checkoutResult?.auto_confirmed ? (
                        <p style={{ fontWeight: '600', marginBottom: '8px' }}>
                          {t('texts.subscription_activated')}
                        </p>
                      ) : (
                        <p style={{ fontWeight: '600', marginBottom: '8px' }}>
                          {t('texts.payment_request_received')}
                        </p>
                      )}
                      {!trialDone && (
                        <p className="text-secondary" style={{ fontSize: '14px' }}>
                          {t('texts.payment_id_label')}: <code>{checkoutResult?.payment_id}</code>
                        </p>
                      )}
                      <p className="text-secondary" style={{ fontSize: '14px', marginTop: '8px' }}>
                        {t('texts.payment_request_already_exists')}
                      </p>
                      <p className="text-secondary" style={{ fontSize: '14px', marginTop: '8px' }}>
                        {t('texts.redirecting_to_profile')}
                      </p>
                    </div>
                  )}

                  {!checkoutResult && (
                    <div className="flex-center gap-3">
                      <button
                        onClick={() => setStep('offer')}
                        className="button"
                        style={{ flex: 1, background: 'var(--bg-tertiary)' }}
                      >
                        {t('buttons.cancel')}
                      </button>
                      <button
                        onClick={selectedTariff.id === 'custom' ? handlePayCustom : handlePay}
                        className="button"
                        style={{ flex: 1 }}
                        disabled={processing}
                      >
                        {processing ? t('texts.waiting') : t('buttons.confirm')}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

