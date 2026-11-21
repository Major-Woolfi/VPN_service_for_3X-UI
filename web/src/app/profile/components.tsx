"use client";

import Link from "next/link";
import type { SanitizedUser, SubscriptionPaymentRequest } from "@/lib/types";

interface ProfileHeaderProps {
  user: SanitizedUser | null;
  t: (key: string, params?: Record<string, string | number>) => string;
}

export function ProfileHeader({ user, t }: ProfileHeaderProps) {
  const initials = (user?.login || user?.username)?.charAt(0).toUpperCase() || "?";
  const hasTid = Boolean(user?.telegram_id);

  return (
    <div className="profile-header no-avatar">
      <div className="profile-avatar profile-avatar-placeholder">{initials}</div>
      <div className="profile-info">
        <h1 className="profile-name">
          {user?.login || user?.username || `${t("texts.user_id")}:${user?.user_id}`}
        </h1>
        <p className="profile-username">
          {t("texts.account")}
          <span style={{ marginLeft: "12px", color: "var(--text-secondary)" }}>
            {t("texts.user_id")}: {user?.user_id}
          </span>
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
        <div
          style={{
            marginTop: "16px",
            paddingTop: "16px",
            borderTop: "1px solid var(--border-color)",
          }}
        >
          {renewError && (
            <div className="error-message" style={{ marginBottom: "12px" }}>
              {renewError}
            </div>
          )}
          {renewResult ? (
            <div className="success-message">
              <p style={{ fontWeight: "600", marginBottom: "8px" }}>
                {t("texts.renew_request_sent")}
              </p>
              <p className="text-secondary" style={{ fontSize: "14px" }}>
                {t("texts.payment_id_label")}: <code>{renewResult.payment_id}</code>
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
        <div className="content-grid" style={{ marginTop: "16px" }}>
          {(isSubscribed || hasAdminSub || user?.partner_subscription?.url) && (
            <Link href="/client" className="button">
              {t("texts.setup_client")}
            </Link>
          )}
          {user?.is_admin && (
            <Link href="/subscribe" className="button">
              {t("buttons.buy")}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
