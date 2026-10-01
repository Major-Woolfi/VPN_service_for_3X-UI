"use client";

import Header from "@/components/Header";
import { useEffect, useState, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { useFeatures } from "@/contexts/FeaturesContext";
import {
  getTariffs,
  createCheckout,
  createTestSubscription,
  generateCustomTariff,
  getLocations,
  trialSubscription,
  getCustomTariffParams,
} from "@/lib/api";
import type {
  Tariff,
  Location,
  CustomTariffParams,
  CheckoutResponse,
  TestSubscriptionResponse,
  PaymentMethod,
} from "@/lib/types";
import TariffGrid from "@/components/TariffGrid";
import { SafeHTML } from "@/components/SafeHTML";

type Step = "select" | "offer" | "payment" | "custom";

function roundHalfToEven(value: number): number {
  const rounded = Math.round(value);
  const fraction = value - Math.floor(value);
  return fraction === 0.5 && rounded % 2 !== 0 ? rounded - 1 : rounded;
}

export default function SubscribePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const { features, loading: featuresLoading } = useFeatures();
  const [tariffs, setTariffs] = useState<Tariff[]>([]);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState<Step>("select");
  const [selectedTariff, setSelectedTariff] = useState<Tariff | null>(null);
  const [urlSelectionDismissed, setUrlSelectionDismissed] = useState(false);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const [checkoutResult, setCheckoutResult] = useState<CheckoutResponse | null>(
    null,
  );
  const [testResult, setTestResult] = useState<TestSubscriptionResponse | null>(
    null,
  );
  const [hasPendingPartnerApplication, setHasPendingPartnerApplication] =
    useState(false);
  const [isPartner, setIsPartner] = useState(false);
  const [userSubscriptionStatus, setUserSubscriptionStatus] = useState("");
  const [userTrustScore, setUserTrustScore] = useState(0);
  const [userDiscountPercent, setUserDiscountPercent] = useState(0);
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
  const [customTariffParams, setCustomTariffParams] =
    useState<CustomTariffParams | null>(null);
  // Тариф, выбранный на главной (?tariff=<id>). Объявлен до эффектов,
  // чтобы редирект гостя на логин его сохранил.
  const requestedTariffId = searchParams.get("tariff");

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [tariffs, locations, customParams] = await Promise.all([
          getTariffs(),
          getLocations(),
          features?.features?.custom_tariff && user
            ? getCustomTariffParams()
            : Promise.resolve(null),
        ]);
        if (!cancelled) {
          setTariffs(tariffs);
          setLocations(locations);
          setCustomTariffParams(customParams);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load tariffs:", err);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user, features?.features?.custom_tariff, router, requestedTariffId]);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      // Сохраняем выбранный тариф: без этого гость возвращался с логина
      // на общий список и терял выбор.
      const next = requestedTariffId
        ? `/subscribe?tariff=${encodeURIComponent(requestedTariffId)}`
        : "/subscribe";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
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
    setUserTrustScore(user.trust_score || 0);
    setUserDiscountPercent(user.discount_percent || 0);
    setLoading(false);
  }, [authLoading, user, router, requestedTariffId]);

  const isSubscribed = userSubscriptionStatus === "active";
  const eligibleForTrial = !trialUsed && !isSubscribed && !isAdmin;
  const canBuy = !isSubscribed && !hasPendingPayment;
  // Админ берёт тестовую подписку без оплаты, поэтому активная подписка
  // и ожидающий платёж его не блокируют (как в боте).
  const canSelect = isAdmin || canBuy;
  const visibleTariffs = useMemo(
    () => tariffs.filter((t) => t.active && (!t.is_trial || eligibleForTrial)),
    [tariffs, eligibleForTrial],
  );

  // Тариф из ?tariff=... показывается сразу, но выбор из URL не должен
  // обходить те же проверки, что и клик по карточке.
  const preselectedTariff = useMemo(
    () =>
      requestedTariffId
        ? (visibleTariffs.find((t) => t.id === requestedTariffId) ?? null)
        : null,
    [requestedTariffId, visibleTariffs],
  );
  const urlBlockedKey = hasPendingPartnerApplication
    ? "texts.partner_application_pending_block"
    : !telegramLinked
      ? "texts.subscription_requires_telegram"
      : !canSelect
        ? "texts.purchase_blocked_wait_admin"
        : "";
  const urlPreselectActive =
    preselectedTariff !== null &&
    !urlSelectionDismissed &&
    !urlBlockedKey &&
    !isAdmin;

  // Активный тариф: явно выбранный пользователем важнее тарифа из URL.
  const activeTariff: Tariff | null = selectedTariff ?? preselectedTariff;
  const activeStep: Step =
    step !== "select" ? step : urlPreselectActive ? "offer" : "select";
  const activeError =
    error ||
    (preselectedTariff && step === "select" && urlBlockedKey
      ? t(urlBlockedKey)
      : "");

  const handleSelectTariff = (tariff: Tariff) => {
    if (hasPendingPartnerApplication) {
      setError(t("texts.partner_application_pending_block"));
      return;
    }
    if (!telegramLinked) {
      setError(t("texts.subscription_requires_telegram"));
      return;
    }
    if (!canSelect) {
      setError(t("texts.purchase_blocked_wait_admin"));
      return;
    }
    if (isAdmin) {
      void handleAdminTestPlan(tariff);
      return;
    }
    setUrlSelectionDismissed(true);
    setSelectedTariff(tariff);
    setStep("offer");
    setError("");
  };

  // Назад из оффера: снимаем и явный выбор, и предвыбор из URL.
  const handleBackToSelect = () => {
    setSelectedTariff(null);
    setUrlSelectionDismissed(true);
    setStep("select");
    setError("");
  };

  const handleAcceptOffer = async () => {
    if (!activeTariff) return;
    if (isAdmin) {
      await handleAdminTestPlan(activeTariff);
      return;
    }
    if (activeTariff.is_trial) {
      await handleTrial();
      return;
    }
    setSelectedTariff(activeTariff);
    setUrlSelectionDismissed(true);
    setStep("payment");
    setError("");
  };

  // Тестовая подписка администратора: оформляется сразу, без оплаты.
  const handleAdminTestPlan = async (tariff: Tariff) => {
    setProcessing(true);
    setError("");
    setUrlSelectionDismissed(true);
    try {
      const result = await createTestSubscription({
        plan_id: tariff.id,
        method: "manual",
        ...(tariff.id === "custom"
          ? {
              custom_plan: {
                name: tariff.name,
                price_rub: tariff.price_rub,
                traffic_gb: tariff.traffic_gb,
                ip_limit: tariff.ip_limit,
                duration_days: tariff.duration_days,
                servers: tariff.servers,
              },
            }
          : {}),
      });
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.checkout_error"));
    } finally {
      setProcessing(false);
    }
  };

  const handleTrial = async () => {
    setProcessing(true);
    setError("");
    try {
      await trialSubscription();
      setTrialDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.checkout_error"));
    } finally {
      setProcessing(false);
    }
  };

  const handlePay = async () => {
    if (!user || !activeTariff) return;
    setProcessing(true);
    setError("");

    if (isPartner && userSubscriptionStatus === "active") {
      setError(t("texts.active_partner_subscription_guard"));
      setProcessing(false);
      return;
    }

    try {
      const result = await createCheckout({
        plan_id: activeTariff.id,
        method: selectedPaymentMethod,
      });
      setCheckoutResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.checkout_error"));
    } finally {
      setProcessing(false);
    }
  };

  const handleCustomTariffChange = async () => {
    if (!user || customPriceLoading) return;
    if (selectedLocations.length < 1) {
      setError(t("texts.custom_tariff_no_locations"));
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
      setError(t("texts.partner_application_pending_block"));
      return;
    }
    if (!telegramLinked) {
      setError(t("texts.subscription_requires_telegram"));
      return;
    }
    if (!canSelect) {
      setError(t("texts.purchase_blocked_wait_admin"));
      return;
    }
    if (selectedLocations.length < 1) {
      setError(t("texts.custom_tariff_no_locations"));
      return;
    }
    if (customPrice === null) {
      setError(t("texts.custom_tariff_error"));
      return;
    }
    const customTariff: Tariff = {
      id: "custom",
      name: `${t("texts.custom_tariff")} ${customTraffic}GB / ${customIp}IP / ${customDays}d`,
      price_rub: customPrice,
      traffic_gb: customTraffic,
      ip_limit: customIp,
      duration_days: customDays,
      servers: selectedLocations,
      active: true,
      locations: selectedLocations,
    };
    setUrlSelectionDismissed(true);
    if (isAdmin) {
      void handleAdminTestPlan(customTariff);
      return;
    }
    setSelectedTariff(customTariff);
    setStep("offer");
    setError("");
  };

  const handlePayCustom = async () => {
    if (!user || !activeTariff) return;
    setProcessing(true);
    setError("");

    if (isPartner && userSubscriptionStatus === "active") {
      setError(t("texts.active_partner_subscription_guard"));
      setProcessing(false);
      return;
    }

    try {
      const result = await createCheckout({
        plan_id: "custom",
        method: selectedPaymentMethod,
        custom_plan: {
          name: activeTariff.name,
          price_rub: activeTariff.price_rub,
          traffic_gb: activeTariff.traffic_gb,
          ip_limit: activeTariff.ip_limit,
          duration_days: activeTariff.duration_days,
          servers: activeTariff.servers,
        },
      });
      setCheckoutResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("texts.checkout_error"));
    } finally {
      setProcessing(false);
    }
  };

  const availableMethods = features?.payment_methods || [];
  const [requestedPaymentMethod, setRequestedPaymentMethod] =
    useState<PaymentMethod>("card");
  const selectedPaymentMethod: PaymentMethod = availableMethods.includes(
    requestedPaymentMethod,
  )
    ? requestedPaymentMethod
    : (availableMethods[0] as PaymentMethod | undefined) || "card";

  const amountInfo = useMemo(() => {
    if (!activeTariff) return null;
    if (checkoutResult) {
      return {
        original: checkoutResult.original_amount_rub,
        discounted: checkoutResult.amount_rub,
        percent: checkoutResult.discount_percent,
      };
    }
    const original = activeTariff.price_rub;
    const percent = userDiscountPercent || 0;
    const discounted = percent
      ? roundHalfToEven(original * (1 - percent / 100))
      : original;
    return { original, discounted, percent };
  }, [checkoutResult, activeTariff, userDiscountPercent]);

  useEffect(() => {
    if ((checkoutResult || trialDone) && !processing) {
      const timer = setTimeout(() => {
        router.push("/profile");
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
                <h1 className="profile-name">{t("texts.loading")}</h1>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  if (availableMethods.length === 0 && !isAdmin) {
    return (
      <>
        <Header currentPage="/subscribe" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t("buttons.buy")}</h1>
                <p className="profile-username">{t("texts.tariffs")}</p>
              </div>
            </div>
            {visibleTariffs.length > 0 ? (
              <div className="pinned-section fade-in">
                <h2>{t("texts.tariffs")}</h2>
                <div className="pinned-content">
                  {!canSelect && (
                    <div
                      className="card"
                      style={{
                        marginBottom: "16px",
                        background: "var(--accent-glow)",
                        border: "1px solid var(--accent)",
                        color: "var(--text-primary)",
                        fontSize: "14px",
                        lineHeight: "1.5",
                      }}
                    >
                      {t("texts.purchase_blocked_wait_admin")}
                    </div>
                  )}
                  <TariffGrid
                    tariffs={visibleTariffs}
                    onSelect={handleSelectTariff}
                  />
                  <div
                    className="card"
                    style={{
                      marginTop: "16px",
                      background: "var(--accent-glow)",
                      border: "1px solid var(--accent)",
                      color: "var(--text-primary)",
                      fontSize: "14px",
                      lineHeight: "1.5",
                    }}
                  >
                    {t("texts.no_payment_methods")}
                  </div>
                </div>
              </div>
            ) : (
              <div className="pinned-section fade-in">
                <div className="pinned-content">
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      textAlign: "center",
                      marginTop: "16px",
                    }}
                  >
                    {t("texts.no_tariffs_available")}
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
              <h1 className="profile-name">{t("buttons.buy")}</h1>
              <p className="profile-username">
                {activeStep === "select" && t("texts.tariffs")}
                {activeStep === "offer" && t("texts.public_offer")}
                {activeStep === "payment" && t("texts.payment_title")}
              </p>
            </div>
          </div>

          {activeError && <div className="error-message">{activeError}</div>}

          {activeStep === "select" && (
            <div className="pinned-section fade-in">
              <h2>{t("texts.tariffs")}</h2>
              <div className="pinned-content">
                {!canSelect && (
                  <div
                    className="card"
                    style={{
                      marginBottom: "16px",
                      background: "var(--accent-glow)",
                      border: "1px solid var(--accent)",
                      color: "var(--text-primary)",
                      fontSize: "14px",
                      lineHeight: "1.5",
                    }}
                  >
                    {t("texts.purchase_blocked_wait_admin")}
                  </div>
                )}
                {isAdmin && (
                  <div
                    className="card"
                    style={{
                      marginBottom: "16px",
                      background: "var(--accent-glow)",
                      border: "1px solid var(--accent)",
                      color: "var(--text-primary)",
                      fontSize: "14px",
                      lineHeight: "1.5",
                    }}
                  >
                    {t("texts.admin_test_mode_hint")}
                  </div>
                )}
                {!telegramLinked && (
                  <div
                    className="card"
                    style={{
                      marginBottom: "16px",
                      background: "var(--accent-glow)",
                      border: "1px solid var(--accent)",
                      color: "var(--text-primary)",
                      fontSize: "14px",
                      lineHeight: "1.5",
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px",
                    }}
                  >
                    <span>{t("texts.subscription_requires_telegram")}</span>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => router.push("/settings")}
                    >
                      {t("buttons.link_telegram")}
                    </button>
                  </div>
                )}
                {visibleTariffs.length === 0 ? (
                  <p style={{ color: "var(--text-secondary)" }}>
                    {t("texts.no_tariffs_available")}
                  </p>
                ) : (
                  <TariffGrid
                    tariffs={visibleTariffs}
                    onSelect={handleSelectTariff}
                  />
                )}
              </div>
            </div>
          )}

          {activeStep === "select" && features?.features?.custom_tariff && (
            <div className="pinned-section fade-in delay-1">
              <h2>{t("texts.custom_tariff")}</h2>
              <div className="pinned-content">
                <div
                  className="card"
                  style={{
                    marginTop: "16px",
                    background: "var(--accent-glow)",
                    border: "1px solid var(--accent)",
                  }}
                >
                  <p
                    className="text-secondary"
                    style={{
                      fontSize: "13px",
                      lineHeight: "1.5",
                      marginBottom: "8px",
                    }}
                  >
                    {t("texts.custom_tariff_description", {
                      min_gb: customTariffParams?.min_gb || 1,
                      max_gb: customTariffParams?.max_gb || 1000,
                      min_ip: customTariffParams?.min_ip || 1,
                      max_ip: customTariffParams?.max_ip || 10,
                      min_days: customTariffParams?.min_days || 1,
                      max_days: customTariffParams?.max_days || 365,
                    })}
                  </p>
                  {customTariffParams && (
                    <div
                      style={{
                        marginTop: "12px",
                        paddingTop: "12px",
                        borderTop: "1px solid var(--border-color)",
                      }}
                    >
                      <div
                        style={{
                          padding: "10px",
                          background: "var(--bg-primary)",
                          borderRadius: "var(--radius-sm)",
                          fontFamily: "monospace",
                          fontSize: "12px",
                          lineHeight: "1.4",
                          marginBottom: "12px",
                          textAlign: "center",
                        }}
                      >
                        <SafeHTML html={t("texts.custom_tariff_formula")} />
                      </div>
                      <p
                        style={{
                          fontSize: "12px",
                          fontWeight: "600",
                          color: "var(--text-primary)",
                          marginBottom: "6px",
                        }}
                      >
                        {t("texts.custom_tariff_formula_params")}
                      </p>
                      <div
                        style={{
                          fontSize: "12px",
                          color: "var(--text-secondary)",
                          lineHeight: "1.6",
                        }}
                      >
                        <div>
                          <SafeHTML html={t("texts.custom_tariff_param_gb")} />
                        </div>
                        <div>
                          <SafeHTML html={t("texts.custom_tariff_param_ip")} />
                        </div>
                        <div>
                          <SafeHTML
                            html={t("texts.custom_tariff_param_days")}
                          />
                        </div>
                        <div style={{ marginTop: "4px" }}>
                          <SafeHTML
                            html={t("texts.custom_tariff_param_locations")}
                          />
                        </div>
                        {customTariffParams.locations.length > 0 ? (
                          <div style={{ marginLeft: "12px", marginTop: "2px" }}>
                            {customTariffParams.locations.map((loc) => (
                              <div key={loc.code}>
                                <SafeHTML
                                  html={t(
                                    "texts.custom_tariff_location_price_line",
                                    {
                                      label:
                                        loc.label || loc.code.toUpperCase(),
                                      price: loc.price_per_day_rub || 0,
                                    },
                                  )}
                                />
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ marginLeft: "12px", marginTop: "2px" }}>
                            <SafeHTML
                              html={t("texts.custom_tariff_no_locations")}
                            />
                          </div>
                        )}
                      </div>
                      <div
                        style={{
                          marginTop: "12px",
                          paddingTop: "8px",
                          borderTop: "1px solid var(--border-color)",
                          fontSize: "11px",
                          color: "var(--text-secondary)",
                        }}
                      >
                        base = {customTariffParams.base_price} ₽ · gb_coef ={" "}
                        {customTariffParams.gb_coef} ₽ · ip_day_coef ={" "}
                        {customTariffParams.ip_day_coef} ₽
                      </div>
                    </div>
                  )}
                </div>
                {!showCustomForm ? (
                  <button
                    onClick={() => setShowCustomForm(true)}
                    className="button"
                    style={{ width: "100%", marginTop: "16px" }}
                  >
                    {t("texts.custom_tariff_collect")}
                  </button>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px",
                      marginTop: "16px",
                    }}
                  >
                    <div
                      style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}
                    >
                      <div style={{ flex: 1, minWidth: "120px" }}>
                        <label
                          style={{
                            fontSize: "12px",
                            color: "var(--text-secondary)",
                            marginBottom: "4px",
                            display: "block",
                          }}
                        >
                          {t("texts.traffic")}
                        </label>
                        <div className="number-input-wrapper">
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              setCustomTraffic(
                                Math.max(
                                  customTariffParams?.min_gb || 1,
                                  customTraffic - 1,
                                ),
                              );
                              setCustomPrice(null);
                            }}
                          >
                            -
                          </button>
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
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              setCustomTraffic(
                                Math.min(
                                  customTariffParams?.max_gb || 1000,
                                  customTraffic + 1,
                                ),
                              );
                              setCustomPrice(null);
                            }}
                          >
                            +
                          </button>
                        </div>
                      </div>
                      <div style={{ flex: 1, minWidth: "120px" }}>
                        <label
                          style={{
                            fontSize: "12px",
                            color: "var(--text-secondary)",
                            marginBottom: "4px",
                            display: "block",
                          }}
                        >
                          {t("texts.ips")}
                        </label>
                        <div className="number-input-wrapper">
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              setCustomIp(
                                Math.max(
                                  customTariffParams?.min_ip || 1,
                                  customIp - 1,
                                ),
                              );
                              setCustomPrice(null);
                            }}
                          >
                            -
                          </button>
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
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              setCustomIp(
                                Math.min(
                                  customTariffParams?.max_ip || 15,
                                  customIp + 1,
                                ),
                              );
                              setCustomPrice(null);
                            }}
                          >
                            +
                          </button>
                        </div>
                      </div>
                      <div style={{ flex: 1, minWidth: "120px" }}>
                        <label
                          style={{
                            fontSize: "12px",
                            color: "var(--text-secondary)",
                            marginBottom: "4px",
                            display: "block",
                          }}
                        >
                          {t("texts.days")}
                        </label>
                        <div className="number-input-wrapper">
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              setCustomDays(
                                Math.max(
                                  customTariffParams?.min_days || 1,
                                  customDays - 1,
                                ),
                              );
                              setCustomPrice(null);
                            }}
                          >
                            -
                          </button>
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
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              setCustomDays(
                                Math.min(
                                  customTariffParams?.max_days || 365,
                                  customDays + 1,
                                ),
                              );
                              setCustomPrice(null);
                            }}
                          >
                            +
                          </button>
                        </div>
                      </div>
                    </div>
                    {locations.length > 0 && (
                      <div>
                        <label
                          style={{
                            fontSize: "12px",
                            color: "var(--text-secondary)",
                            marginBottom: "4px",
                            display: "block",
                          }}
                        >
                          {t("texts.locations")}
                        </label>
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "8px",
                          }}
                        >
                          {locations.map((loc) => {
                            const isSelected = selectedLocations.includes(
                              loc.code,
                            );
                            return (
                              <button
                                key={loc.code}
                                type="button"
                                onClick={() => {
                                  setSelectedLocations((prev) =>
                                    isSelected
                                      ? prev.filter((c) => c !== loc.code)
                                      : [...prev, loc.code],
                                  );
                                  setCustomPrice(null);
                                }}
                                className="card"
                                style={{
                                  padding: "8px 12px",
                                  fontSize: "13px",
                                  cursor: "pointer",
                                  background: isSelected
                                    ? "var(--accent-glow)"
                                    : undefined,
                                  border: isSelected
                                    ? "1px solid var(--accent)"
                                    : undefined,
                                  display: "flex",
                                  alignItems: "center",
                                  gap: "6px",
                                }}
                              >
                                <span>{loc.flag}</span>
                                <span>{loc.code.toUpperCase()}</span>
                                {loc.price_per_day_rub && (
                                  <span
                                    style={{
                                      fontSize: "11px",
                                      color: "var(--text-secondary)",
                                    }}
                                  >
                                    +{loc.price_per_day_rub}₽
                                    {t("texts.per_day_short")}
                                  </span>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {customPrice !== null && (
                      <div
                        style={{
                          padding: "12px",
                          background: "var(--accent-glow)",
                          borderRadius: "var(--radius-sm)",
                          textAlign: "center",
                        }}
                      >
                        <span
                          style={{
                            fontSize: "18px",
                            fontWeight: "700",
                            color: "var(--accent)",
                          }}
                        >
                          {customPrice} ₽
                        </span>
                      </div>
                    )}
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        onClick={() => {
                          setShowCustomForm(false);
                          setCustomPrice(null);
                        }}
                        className="button"
                        style={{ flex: 1, background: "var(--bg-tertiary)" }}
                      >
                        {t("buttons.cancel")}
                      </button>
                      <button
                        onClick={handleCustomTariffChange}
                        className="button"
                        style={{ flex: 1, background: "var(--bg-tertiary)" }}
                        disabled={customPriceLoading}
                      >
                        {customPriceLoading
                          ? t("texts.loading")
                          : t("texts.calculate_price")}
                      </button>
                      <button
                        onClick={handleSelectCustomTariff}
                        className="button"
                        style={{ flex: 1 }}
                        disabled={customPrice === null || customPriceLoading}
                      >
                        {t("texts.select_custom_tariff")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeStep === "offer" && activeTariff && (
            <div className="pinned-section fade-in">
              <h2>{t("texts.public_offer")}</h2>
              <div className="pinned-content">
                <div className="mt-4">
                  <div className="card" style={{ marginBottom: "16px" }}>
                    <h3>{activeTariff.name}</h3>
                    <p
                      className="text-secondary"
                      style={{ fontSize: "14px", marginTop: "8px" }}
                    >
                      {activeTariff.price_rub} ₽ ·{" "}
                      {t("texts.duration_days", {
                        days: activeTariff.duration_days,
                      })}{" "}
                      ·{" "}
                      {activeTariff.traffic_gb === 0
                        ? t("texts.unlimited")
                        : t("texts.traffic_gb", {
                            value: activeTariff.traffic_gb,
                          })}{" "}
                      · {activeTariff.ip_limit} {t("texts.ips")}
                    </p>
                  </div>
                  <p
                    className="text-secondary"
                    style={{ fontSize: "14px", lineHeight: "1.6" }}
                  >
                    {t("texts.offer_text_1")} {t("texts.offer_text_2")}{" "}
                    {t("texts.offer_text_3")}
                  </p>
                  <blockquote className="mt-4">
                    {t("texts.offer_section_2")}: {t("texts.offer_text_2")}
                  </blockquote>
                  <div className="flex-center gap-3 mt-4">
                    <button
                      onClick={handleBackToSelect}
                      className="button"
                      style={{ flex: 1, background: "var(--bg-tertiary)" }}
                    >
                      {t("buttons.cancel")}
                    </button>
                    <button
                      onClick={handleAcceptOffer}
                      className="button"
                      style={{ flex: 1 }}
                    >
                      {t("buttons.continue")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeStep === "payment" &&
            activeTariff &&
            availableMethods.length > 0 && (
              <div className="pinned-section fade-in">
                <h2>{t("texts.payment_title")}</h2>
                <div className="pinned-content">
                  <div className="mt-4">
                    <div className="card" style={{ marginBottom: "24px" }}>
                      <div className="mb-4">
                        <span className="text-secondary">
                          {t("texts.plan")}:{" "}
                        </span>
                        <span style={{ fontWeight: "600" }}>
                          {activeTariff.name}
                        </span>
                      </div>
                      <div className="mb-4">
                        <span className="text-secondary">
                          {t("texts.payment_methods")}:{" "}
                        </span>
                        <div
                          className="flex-center gap-3"
                          style={{ marginTop: "12px" }}
                        >
                          {availableMethods.includes("yoomoney") && (
                            <button
                              type="button"
                              className="button"
                              aria-pressed={
                                selectedPaymentMethod === "yoomoney"
                              }
                              style={{
                                flex: 1,
                                background:
                                  selectedPaymentMethod === "yoomoney"
                                    ? undefined
                                    : "var(--bg-tertiary)",
                              }}
                              onClick={() =>
                                setRequestedPaymentMethod("yoomoney")
                              }
                            >
                              {t("texts.yoomoney")}
                            </button>
                          )}
                          {availableMethods.includes("card") && (
                            <button
                              type="button"
                              className="button"
                              aria-pressed={selectedPaymentMethod === "card"}
                              style={{
                                flex: 1,
                                background:
                                  selectedPaymentMethod === "card"
                                    ? undefined
                                    : "var(--bg-tertiary)",
                              }}
                              onClick={() => setRequestedPaymentMethod("card")}
                            >
                              {t("texts.p2p")}
                            </button>
                          )}
                        </div>
                      </div>
                      {userTrustScore > 0 && (
                        <div className="mb-4">
                          <span className="text-secondary">
                            {t("texts.trust_score")}:{" "}
                          </span>
                          <span style={{ fontWeight: "600" }}>
                            {userTrustScore}
                          </span>
                        </div>
                      )}
                      {amountInfo && amountInfo.percent > 0 && (
                        <div className="mb-4">
                          <span className="text-secondary">
                            {t("texts.discount")}:{" "}
                          </span>
                          <span style={{ fontWeight: "600" }}>
                            {amountInfo.percent}%
                          </span>
                        </div>
                      )}
                      <div className="mb-4">
                        <span className="text-secondary">
                          {t("texts.amount")}:{" "}
                        </span>
                        {amountInfo && amountInfo.percent > 0 ? (
                          <span
                            style={{
                              fontWeight: "700",
                              fontSize: "18px",
                              color: "var(--accent)",
                            }}
                          >
                            <s style={{ opacity: 0.5 }}>
                              {amountInfo.original} ₽
                            </s>{" "}
                            → {amountInfo.discounted} ₽
                          </span>
                        ) : (
                          <span
                            style={{
                              fontWeight: "700",
                              fontSize: "18px",
                              color: "var(--accent)",
                            }}
                          >
                            {amountInfo?.discounted ?? activeTariff.price_rub} ₽
                          </span>
                        )}
                      </div>
                    </div>

                    {(checkoutResult || trialDone) && (
                      <div
                        className="success-message"
                        style={{ marginBottom: "24px" }}
                      >
                        {trialDone ? (
                          <p style={{ fontWeight: "600", marginBottom: "8px" }}>
                            {t("texts.trial_activated")}
                          </p>
                        ) : (
                          <p style={{ fontWeight: "600", marginBottom: "8px" }}>
                            {t("texts.payment_request_received")}
                          </p>
                        )}
                        {!trialDone && (
                          <>
                            <p
                              className="text-secondary"
                              style={{ fontSize: "14px" }}
                            >
                              {t("texts.payment_id_label")}:{" "}
                              <code>{checkoutResult?.payment_id}</code>
                            </p>
                            {checkoutResult?.payment_method === "card" &&
                              checkoutResult?.payment_details?.card_number && (
                                <p
                                  className="text-secondary"
                                  style={{ fontSize: "14px", marginTop: "8px" }}
                                >
                                  {t("texts.p2p")}:{" "}
                                  <code>
                                    {
                                      checkoutResult?.payment_details
                                        ?.card_number
                                    }
                                  </code>
                                </p>
                              )}
                          </>
                        )}
                        <p
                          className="text-secondary"
                          style={{ fontSize: "14px", marginTop: "8px" }}
                        >
                          {t("texts.redirecting_to_profile")}
                        </p>
                        {!trialDone && checkoutResult?.checkout_url && (
                          <a
                            href={checkoutResult.checkout_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="button"
                            style={{
                              width: "100%",
                              display: "block",
                              textAlign: "center",
                              textDecoration: "none",
                              marginTop: "12px",
                            }}
                          >
                            {t("texts.pay_now")}
                          </a>
                        )}
                      </div>
                    )}

                    {!checkoutResult && trialDone === false && (
                      <div className="flex-center gap-3">
                        <button
                          onClick={() => {
                            setSelectedTariff(activeTariff);
                            setUrlSelectionDismissed(true);
                            setStep("offer");
                          }}
                          className="button"
                          style={{ flex: 1, background: "var(--bg-tertiary)" }}
                        >
                          {t("buttons.cancel")}
                        </button>
                        <button
                          onClick={
                            activeTariff.id === "custom"
                              ? handlePayCustom
                              : handlePay
                          }
                          className="button"
                          style={{ flex: 1 }}
                          disabled={processing}
                        >
                          {processing
                            ? t("texts.waiting")
                            : t("buttons.confirm")}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

          {testResult && (
            <div className="pinned-section fade-in">
              <h2>{t("texts.subscription_link")}</h2>
              <div className="pinned-content">
                <div
                  className="success-message"
                  style={{ marginBottom: "16px" }}
                >
                  <p style={{ fontWeight: "600", marginBottom: "8px" }}>
                    {t("texts.test_subscription_created_short", {
                      plan_name: testResult.plan_name,
                    })}
                  </p>
                  <p className="text-secondary" style={{ fontSize: "14px" }}>
                    {t("texts.test_subscription_awaiting_admin")}
                  </p>
                </div>
                <Link
                  href="/profile"
                  className="button"
                  style={{
                    display: "block",
                    textAlign: "center",
                    textDecoration: "none",
                    marginTop: "16px",
                  }}
                >
                  {t("texts.account")}
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
