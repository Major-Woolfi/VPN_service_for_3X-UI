"use client";

import Link from "next/link";
import type {
  SanitizedUser,
  SubscriptionPaymentRequest,
} from "@/lib/types";

interface ProfileHeaderProps {
  user: SanitizedUser | null;
  t: (key: string, params?: Record<string, string | number>) => string;
}

export function ProfileHeader({ user, t }: ProfileHeaderProps) {
  const initials = (user?.login || user?.username)?.charAt(0).toUpperCase() || "?";
  const hasTid = Boolean(user?.telegram_id);

  return (
    <div className="profile-header no-avatar">
      <div className="profile-avatar profile-avatar-placeholder">
        {initials}
      </div>
      <div className="profile-info">
        <h1 className="profile-name">
          {user?.login || user?.username || `${t("texts.user_id")}:${user?.user_id}`}
        </h1>
        <p className="profile-username">
          {t("texts.account")}
          {hasTid && (
            <span style={{ marginLeft: "12px", color: "var(--text-secondary)" }}>
              {t("texts.telegram_id_label")}: {user?.telegram_id}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

export function ProfileStatusBadge({
  isSubscribed,
  hasAdminSub,
  t,
}: {
  isSubscribed: boolean;
  hasAdminSub: boolean;
  t: (key: string, params?: Record<string, string | number>) => string;
}) {
  return (
    <>
      <div style={{ color: "var(--text-secondary)" }}>{t("texts.status")}:</div>
      <span
        style={{
          color: isSubscribed || hasAdminSub ? "var(--success)" : "var(--text-secondary)",
          fontWeight: "600",
        }}
      >
        {isSubscribed || hasAdminSub ? t("texts.status_active") : t("texts.no_subscription")}
      </span>
    </>
  );
}

export function ProfileStats({
  user,
  sub,
  t,
  lang,
}: {
  user: SanitizedUser | null;
  sub: {
    status?: string;
    used_gb?: number;
    traffic_gb?: number;
    ip_limit?: number;
    expiry_sub_datatime?: string;
    plan_text?: string;
  } | null | undefined;
  t: (key: string, params?: Record<string, string | number>) => string;
  lang: string;
}) {
  const trafficUsed = sub?.used_gb || 0;
  const trafficTotal = sub?.traffic_gb || 0;
  const expiryDate = sub?.expiry_sub_datatime || "";
  const formattedExpiry = expiryDate ? new Date(expiryDate).toLocaleDateString(lang) : "-";
  const hasAdminSub = Boolean(user?.is_admin && user?.admin_subscription?.url);
  const isAdminSub = hasAdminSub && !(sub?.status === "active");
  const planText = isAdminSub ? t("texts.admin_plan") : sub?.plan_text || "-";
  const displayTrafficTotal =
    isAdminSub || trafficTotal === 0 ? t("texts.unlimited") : t("texts.traffic_gb", { value: trafficTotal });
  const displayIps = isAdminSub ? t("texts.unlimited") : sub?.ip_limit || 0;

  return (
    <div className="pinned-section fade-in">
      <h2>{t("texts.subscription_status")}</h2>
      <div className="pinned-content">
        <div style={{ marginTop: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
            <span style={{ color: "var(--text-secondary)" }}>{t("texts.status_active")}</span>
            <span style={{ color: "var(--success)", fontWeight: "600" }}>{t("texts.status_active")}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
            <span style={{ color: "var(--text-secondary)" }}>{t("texts.plan")}</span>
            <span>{planText}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
            <span style={{ color: "var(--text-secondary)" }}>{t("texts.expires")}</span>
            <span>{formattedExpiry}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
            <span style={{ color: "var(--text-secondary)" }}>{t("texts.traffic")}</span>
            <span>{t("texts.traffic_gb", { value: trafficUsed })} / {displayTrafficTotal}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
            <span style={{ color: "var(--text-secondary)" }}>{t("texts.ips")}</span>
            <span>{displayIps}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-secondary)" }}>{t("texts.trust_score")}</span>
            <span>{user?.trust_score || 0} ({user?.discount_percent || 0}% {t("texts.discount")})</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ProfileRenewForm({
  user,
  renewLoading,
  renewResult,
  renewError,
  handleRenew,
  t,
}: {
  user: SanitizedUser | null;
  renewLoading: boolean;
  renewResult: SubscriptionPaymentRequest | null;
  renewError: string;
  handleRenew: () => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}) {
  return (
    <div className="pinned-section fade-in">
      <div className="pinned-content">
        <div style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid var(--border-color)" }}>
          {renewError && (
            <div className="error-message" style={{ marginBottom: "12px" }}>
              {renewError}
            </div>
          )}
          {renewResult ? (
            <div className="success-message">
              <p style={{ fontWeight: "600", marginBottom: "8px" }}>{t("texts.renew_request_sent")}</p>
              <p className="text-secondary" style={{ fontSize: "14px" }}>
                {t("texts.payment_id_label")}:{" "}
                <code>{renewResult.payment_id}</code>
              </p>
              {renewResult.discount_percent > 0 && (
                <p className="text-secondary" style={{ fontSize: "14px", marginTop: "8px" }}>
                  {t("texts.amount")}:{" "}
                  <s style={{ opacity: 0.5 }}>{renewResult.original_amount_rub} ₽</s>
                  {" → "}
                  {renewResult.amount} ₽ ({renewResult.discount_percent}% {t("texts.discount")})
                </p>
              )}
              <p className="text-secondary" style={{ fontSize: "14px", marginTop: "8px" }}>
                {t("texts.renew_wait_admin")}
              </p>
              <button onClick={handleRenew} disabled={renewLoading} className="button" style={{ width: "100%", marginTop: "12px" }}>
                {t("texts.renew_check_status")}
              </button>
            </div>
          ) : (
            <button onClick={handleRenew} disabled={renewLoading || user?.has_pending_payment} className="button" style={{ width: "100%" }}>
              {renewLoading ? t("texts.loading") : t("buttons.renew_subscription")}
            </button>
          )}
          {user?.has_pending_payment && !renewResult && (
            <p className="text-secondary" style={{ fontSize: "13px", marginTop: "8px" }}>
              {t("texts.purchase_blocked_wait_admin")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function ProfileActions({
  isSubscribed,
  hasAdminSub,
  user,
  t,
}: {
  isSubscribed: boolean;
  hasAdminSub: boolean;
  user: SanitizedUser | null;
  t: (key: string, params?: Record<string, string | number>) => string;
}) {
  return (
    <div className="pinned-section fade-in delay-3">
      <h2>{t("texts.actions")}</h2>
      <div className="pinned-content">
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" }}>
          {(isSubscribed || hasAdminSub || user?.partner_subscription?.url) && (
            <Link href="/client" className="button" style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
              {t("texts.setup_client")}
            </Link>
          )}
          {user?.is_admin && (
            <Link href="/subscribe" className="button" style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
              {t("buttons.buy")}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
