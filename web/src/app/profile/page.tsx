"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import { CopyableUrl } from "@/components/CopyableUrl";
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { getSubscriptionLink, renewSubscription } from "@/lib/api";
import type {
  SubscriptionLinkResponse,
  SubscriptionPaymentRequest,
} from "@/lib/types";

export default function ProfilePage() {
  const { user, loading: authLoading, refreshUser } = useAuth();
  const { t, lang } = useLanguage();
  const router = useRouter();
  const [fetchedSubLink, setFetchedSubLink] = useState<{
    key: string;
    link: SubscriptionLinkResponse | null;
  } | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [renewLoading, setRenewLoading] = useState(false);
  const [renewResult, setRenewResult] =
    useState<SubscriptionPaymentRequest | null>(null);
  const [renewError, setRenewError] = useState("");

  // У админа ссылка приходит из профиля, у остальных - запросом на бот.
  const hasAdminSub = Boolean(user?.is_admin && user?.admin_subscription?.url);
  const needsSubLinkFetch =
    Boolean(user) && !hasAdminSub && user?.subscription?.status === "active";
  // Ключ сбрасывает результат запроса при смене пользователя или тарифа.
  const subLinkKey = `${user?.user_id ?? 0}:${user?.subscription?.plan_id ?? ""}`;

  const handleCopy = async (text: string, type: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    }
  };

  const handleRenew = useCallback(async () => {
    if (!user) return;
    setRenewLoading(true);
    setRenewError("");
    try {
      const plan = user.subscription?.plan_id || "default";
      const result = await renewSubscription({ plan_id: plan });
      setRenewResult(result);
      await refreshUser();
    } catch (err) {
      setRenewError(
        err instanceof Error ? err.message : t("texts.renew_request_error"),
      );
    } finally {
      setRenewLoading(false);
    }
  }, [user, refreshUser, t]);

  // Загрузка ссылки выводится из состояния, а не из флага в эффекте:
  // ранний return раньше оставлял страницу в вечной загрузке.
  useEffect(() => {
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent("/profile")}`);
      return;
    }
    if (!needsSubLinkFetch) return;
    const aborter = new AbortController();
    getSubscriptionLink(aborter.signal)
      .then((link) => setFetchedSubLink({ key: subLinkKey, link }))
      .catch(() => setFetchedSubLink({ key: subLinkKey, link: null }));
    return () => aborter.abort();
  }, [user, router, needsSubLinkFetch, subLinkKey]);

  const subLink = hasAdminSub
    ? {
        subscription_id: "Admin",
        vpn_url: user?.admin_subscription?.url || "",
        json_vpn_url: user?.admin_subscription?.json_url || "",
        plan_text: "",
        traffic_gb: 0,
        ip_limit: 0,
        plan_servers: [],
      }
    : fetchedSubLink?.key === subLinkKey
      ? fetchedSubLink.link
      : null;
  const loading =
    authLoading || (needsSubLinkFetch && fetchedSubLink?.key !== subLinkKey);

  if (authLoading || loading || !user) {
    return (
      <>
        <Header currentPage="/profile" />
        <main>
          <div className="profile">
            <div className="pinned-section">
              <p>{t("texts.loading")}</p>
            </div>
          </div>
        </main>
      </>
    );
  }

  const sub = user?.subscription;
  const isSubscribed = sub?.status === "active";
  const isAdminSub = hasAdminSub && !isSubscribed;

  const trafficUsed = sub?.used_gb || 0;
  const trafficTotal = sub?.traffic_gb || 0;
  const trafficPercent =
    trafficTotal > 0 ? Math.round((trafficUsed / trafficTotal) * 100) : 0;
  const expiryDate = sub?.expiry_sub_datatime || "";
  const formattedExpiry = expiryDate
    ? new Date(expiryDate).toLocaleDateString(lang)
    : "-";
  const planText = isAdminSub ? t("texts.admin_plan") : sub?.plan_text || "-";
  const displayTrafficTotal =
    isAdminSub || trafficTotal === 0
      ? t("texts.unlimited")
      : t("texts.traffic_gb", { value: trafficTotal });
  const displayIps = isAdminSub ? t("texts.unlimited") : sub?.ip_limit || 0;

  const initials = user?.username?.charAt(0).toUpperCase() || "?";
  const hasTid = Boolean(user?.telegram_id);

  // Блок ссылок показывается только если есть хотя бы одна реальная ссылка.
  // Без настроенного basepath бот отдаёт пустые url, и раньше здесь
  // рендерился блок, содержащий только sub_id без самой ссылки.
  const hasSubLink = Boolean(
    subLink?.vpn_url ||
    subLink?.json_vpn_url ||
    user?.partner_subscription?.url ||
    user?.partner_subscription?.json_url,
  );

  const renderCopyableUrl = (
    url: string,
    copyType: string,
    isCopied: string | null,
  ) => (
    <CopyableUrl
      url={url}
      copied={isCopied === copyType}
      onCopy={() => handleCopy(url, copyType)}
    />
  );

  return (
    <>
      <Header currentPage="/profile" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-avatar profile-avatar-placeholder">
              {initials}
            </div>
            <div className="profile-info">
              <h1 className="profile-name">
                {user?.username || `${t("texts.user_id")}:${user?.user_id}`}
              </h1>
              <p className="profile-username">
                {t("texts.account")}
                {hasTid && (
                  <span
                    style={{
                      marginLeft: "12px",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {t("texts.telegram_id_label")}: {user?.telegram_id}
                  </span>
                )}
              </p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t("texts.subscription_status")}</h2>
            <div className="pinned-content">
              <div
                style={{
                  marginTop: "16px",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <span style={{ color: "var(--text-secondary)" }}>
                  {t("texts.status")}:
                </span>
                <span
                  style={{
                    color:
                      isSubscribed || hasAdminSub
                        ? "var(--success)"
                        : "var(--text-secondary)",
                    fontWeight: "600",
                  }}
                >
                  {isSubscribed || hasAdminSub
                    ? t("texts.status_active")
                    : t("texts.no_subscription")}
                </span>
              </div>
            </div>
          </div>

          {!isSubscribed && !hasAdminSub ? (
            <div className="pinned-section fade-in">
              <h2>{t("texts.no_subscription")}</h2>
              <div className="pinned-content">
                <p
                  style={{ marginTop: "16px", color: "var(--text-secondary)" }}
                >
                  {t("texts.no_subscription_text")}
                </p>
                <Link
                  href="/subscribe"
                  className="button"
                  style={{
                    display: "inline-block",
                    marginTop: "16px",
                    textDecoration: "none",
                  }}
                >
                  {t("buttons.buy")}
                </Link>
              </div>
            </div>
          ) : (
            <>
              <div className="pinned-section fade-in">
                <h2>{t("texts.subscription_status")}</h2>
                <div className="pinned-content">
                  <div style={{ marginTop: "16px" }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "16px",
                        paddingBottom: "16px",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>
                        {t("texts.status_active")}
                      </span>
                      <span
                        style={{ color: "var(--success)", fontWeight: "600" }}
                      >
                        {t("texts.status_active")}
                      </span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "16px",
                        paddingBottom: "16px",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>
                        {t("texts.plan")}
                      </span>
                      <span>{planText}</span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "16px",
                        paddingBottom: "16px",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>
                        {t("texts.expires")}
                      </span>
                      <span>{formattedExpiry}</span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "16px",
                        paddingBottom: "16px",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>
                        {t("texts.traffic")}
                      </span>
                      <span>
                        {t("texts.traffic_gb", { value: trafficUsed })} /{" "}
                        {displayTrafficTotal}
                      </span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "16px",
                        paddingBottom: "16px",
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>
                        {t("texts.ips")}
                      </span>
                      <span>{displayIps}</span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>
                        {t("texts.trust_score")}
                      </span>
                      <span>
                        {user?.trust_score || 0} ({user?.discount_percent || 0}%{" "}
                        {t("texts.discount")})
                      </span>
                    </div>
                    <div
                      style={{
                        marginTop: "16px",
                        paddingTop: "16px",
                        borderTop: "1px solid var(--border-color)",
                      }}
                    >
                      {renewError && (
                        <div
                          className="error-message"
                          style={{ marginBottom: "12px" }}
                        >
                          {renewError}
                        </div>
                      )}
                      {renewResult ? (
                        <div className="success-message">
                          <p style={{ fontWeight: "600", marginBottom: "8px" }}>
                            {t("texts.renew_request_sent")}
                          </p>
                          <p
                            className="text-secondary"
                            style={{ fontSize: "14px" }}
                          >
                            {t("texts.payment_id_label")}:{" "}
                            <code>{renewResult.payment_id}</code>
                          </p>
                          {renewResult.discount_percent > 0 && (
                            <p
                              className="text-secondary"
                              style={{ fontSize: "14px", marginTop: "8px" }}
                            >
                              {t("texts.amount")}:{" "}
                              <s style={{ opacity: 0.5 }}>
                                {renewResult.original_amount_rub} ₽
                              </s>{" "}
                              → {renewResult.amount} ₽ (
                              {renewResult.discount_percent}%{" "}
                              {t("texts.discount")})
                            </p>
                          )}
                          <p
                            className="text-secondary"
                            style={{ fontSize: "14px", marginTop: "8px" }}
                          >
                            {t("texts.renew_wait_admin")}
                          </p>
                          <button
                            onClick={handleRenew}
                            disabled={renewLoading}
                            className="button"
                            style={{ width: "100%", marginTop: "12px" }}
                          >
                            {t("texts.renew_check_status")}
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={handleRenew}
                          disabled={renewLoading || user?.has_pending_payment}
                          className="button"
                          style={{ width: "100%" }}
                        >
                          {renewLoading
                            ? t("texts.loading")
                            : t("buttons.renew_subscription")}
                        </button>
                      )}
                      {user?.has_pending_payment && !renewResult && (
                        <p
                          className="text-secondary"
                          style={{ fontSize: "13px", marginTop: "8px" }}
                        >
                          {t("texts.purchase_blocked_wait_admin")}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="pinned-section fade-in delay-1">
                <h2>{t("texts.traffic_progress")}</h2>
                <div className="pinned-content">
                  <div style={{ marginTop: "16px" }}>
                    <div
                      style={{
                        height: "24px",
                        background: "var(--bg-tertiary)",
                        borderRadius: "var(--radius-sm)",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          height: "100%",
                          width: `${trafficPercent}%`,
                          background:
                            trafficPercent > 80
                              ? "var(--danger)"
                              : "linear-gradient(90deg, var(--accent), var(--accent-hover))",
                          borderRadius: "var(--radius-sm)",
                          transition: "width 0.3s ease",
                        }}
                      />
                    </div>
                    <p
                      style={{
                        marginTop: "8px",
                        fontSize: "14px",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {trafficTotal === 0
                        ? t("texts.unlimited")
                        : t("texts.traffic_used", {
                            percent: trafficPercent,
                            total: trafficTotal,
                          })}
                    </p>
                  </div>
                </div>
              </div>

              {(isSubscribed ||
                (user?.is_admin && user?.admin_subscription?.url)) &&
                hasSubLink && (
                  <div className="pinned-section fade-in delay-2">
                    <h2>{t("texts.subscription_link")}</h2>
                    <div className="pinned-content">
                      <div
                        style={{
                          marginTop: "16px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "12px",
                        }}
                      >
                        {subLink?.vpn_url &&
                          renderCopyableUrl(subLink.vpn_url, "vpn", copied)}
                        {subLink?.json_vpn_url &&
                          renderCopyableUrl(
                            subLink.json_vpn_url,
                            "json",
                            copied,
                          )}
                      </div>
                    </div>
                  </div>
                )}

              {user?.is_admin &&
                (user.admin_test_subscription?.url ||
                  user.admin_test_subscription?.json_url) && (
                  <div className="pinned-section fade-in delay-2">
                    <h2>{t("texts.test_subscription")}</h2>
                    <div className="pinned-content">
                      <div
                        style={{
                          marginTop: "16px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "12px",
                        }}
                      >
                        {user.admin_test_subscription?.url &&
                          renderCopyableUrl(
                            user.admin_test_subscription.url,
                            "admin-test-vpn",
                            copied,
                          )}
                        {user.admin_test_subscription?.json_url &&
                          renderCopyableUrl(
                            user.admin_test_subscription.json_url,
                            "admin-test-json",
                            copied,
                          )}
                      </div>
                    </div>
                  </div>
                )}

              {user?.is_partner &&
                (user.partner_subscription?.url ||
                  user.partner_subscription?.json_url) && (
                  <div className="pinned-section fade-in delay-2">
                    <h2>{t("texts.partner_subscription")}</h2>
                    <div className="pinned-content">
                      <div
                        style={{
                          marginTop: "16px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "12px",
                        }}
                      >
                        {user.partner_subscription?.url &&
                          renderCopyableUrl(
                            user.partner_subscription.url,
                            "partner-vpn",
                            copied,
                          )}
                        {user.partner_subscription?.json_url &&
                          renderCopyableUrl(
                            user.partner_subscription.json_url,
                            "partner-json",
                            copied,
                          )}
                        {(() => {
                          const pUsed = user.partner_subscription?.used_gb ?? 0;
                          const pTotal =
                            user.partner_subscription?.traffic_gb ?? 0;
                          const pDisplayTotal =
                            pTotal === 0
                              ? t("texts.unlimited")
                              : t("texts.traffic_gb", { value: pTotal });
                          return (
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "space-between",
                              }}
                            >
                              <span style={{ color: "var(--text-secondary)" }}>
                                {t("texts.traffic")}
                              </span>
                              <span>
                                {t("texts.traffic_gb", { value: pUsed })} /{" "}
                                {pDisplayTotal}
                              </span>
                            </div>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                )}

              <div className="pinned-section fade-in delay-3">
                <h2>{t("texts.actions")}</h2>
                <div className="pinned-content">
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px",
                      marginTop: "16px",
                    }}
                  >
                    {(isSubscribed ||
                      user?.admin_subscription?.url ||
                      user?.admin_subscription?.json_url ||
                      user?.partner_subscription?.url) && (
                      <Link
                        href="/client"
                        className="button"
                        style={{
                          display: "block",
                          textAlign: "center",
                          textDecoration: "none",
                        }}
                      >
                        {t("texts.setup_client")}
                      </Link>
                    )}
                    {user?.is_admin && (
                      <Link
                        href="/subscribe"
                        className="button"
                        style={{
                          display: "block",
                          textAlign: "center",
                          textDecoration: "none",
                        }}
                      >
                        {t("buttons.buy")}
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </>
  );
}
