"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import { StatGrid } from "@/components/StatGrid";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  getCoOwnerPayments,
  getCoOwnerProfile,
  getCoOwnerStats,
  rotateCoOwnerLink,
} from "@/lib/api";
import { getErrorMessage } from "@/lib/error";
import type {
  CoOwnerPaymentsResponse,
  CoOwnerProfileResponse,
  CoOwnerStatsResponse,
} from "@/lib/types";

export default function CoOwnerStatsPage() {
  const { user, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();

  const [profile, setProfile] = useState<CoOwnerProfileResponse | null>(null);
  const [stats, setStats] = useState<CoOwnerStatsResponse | null>(null);
  const [payments, setPayments] = useState<CoOwnerPaymentsResponse | null>(null);
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);
  const [rotating, setRotating] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user?.user_id) {
      router.replace("/login?next=/co-owners/stats");
      return;
    }
    if (!user.is_coowner) {
      router.replace("/profile");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [p, s, pay] = await Promise.all([
          getCoOwnerProfile(),
          getCoOwnerStats(),
          getCoOwnerPayments(),
        ]);
        if (!cancelled) {
          setProfile(p);
          setStats(s);
          setPayments(pay);
        }
      } catch (err) {
        if (!cancelled) {
          setMessage(getErrorMessage(err));
          setIsError(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, router, user?.is_coowner, user?.user_id]);

  const handleRotate = async () => {
    setRotating(true);
    setMessage("");
    try {
      const link = await rotateCoOwnerLink();
      setProfile((current) => (current ? { ...current, ...link } : current));
      setMessage(t("texts.co_owner_link_rotated"));
      setIsError(false);
    } catch (err) {
      setMessage(getErrorMessage(err));
      setIsError(true);
    } finally {
      setRotating(false);
    }
  };

  const infoRow = (label: string, value: ReactNode) => (
    <div className="dashboard-row">
      <span className="text-secondary">{label}</span>
      <span>{value}</span>
    </div>
  );

  return (
    <>
      <Header currentPage="/co-owners/stats" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.co_owner_stats")}</h1>
              <p className="profile-username">{t("texts.co_owner_stats_subtitle")}</p>
            </div>
          </div>

          {message ? (
            <div
              className={isError ? "error-message" : "success-message"}
              style={{ marginTop: "12px" }}
            >
              {message}
            </div>
          ) : null}

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <p className="info-block" style={{ marginTop: "16px" }}>
                {t("texts.co_owner_stats_explanation")}
              </p>
            </div>
          </div>

          {profile ? (
            <div className="pinned-section fade-in delay-1">
              <h2>{t("texts.co_owner_profile")}</h2>
              <div className="pinned-content">
                <div style={{ marginTop: "16px" }}>
                  {infoRow(t("texts.co_owner_nickname"), profile.nickname)}
                  {infoRow(t("texts.co_owner_telegram_id"), profile.telegram_id)}
                  {infoRow(t("texts.co_owner_ref_code"), profile.ref_code)}
                  {infoRow(
                    t("texts.co_owner_telegram_link"),
                    profile.telegram_link ? (
                      <a
                        className="referral-link"
                        href={profile.telegram_link}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {profile.telegram_link}
                      </a>
                    ) : (
                      t("texts.not_specified")
                    ),
                  )}
                  {infoRow(
                    t("texts.co_owner_web_link"),
                    profile.web_link ? (
                      <a
                        className="referral-link"
                        href={profile.web_link}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {profile.web_link}
                      </a>
                    ) : (
                      t("texts.not_specified")
                    ),
                  )}
                  {infoRow(
                    t("texts.co_owner_subscription"),
                    `${profile.subscription_id || "-"} / ${profile.vpn_url || "-"}`,
                  )}
                  {infoRow(t("texts.co_owner_expiry"), profile.expiry || t("texts.not_specified"))}
                  {infoRow(
                    t("texts.co_owner_commission_percent"),
                    `${profile.commission_percent}%`,
                  )}
                </div>
                <div className="dashboard-actions">
                  <button
                    type="button"
                    className="button"
                    onClick={handleRotate}
                    disabled={rotating}
                  >
                    {t("buttons.rotate_link")}
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {stats ? (
            <>
              <div className="pinned-section fade-in delay-2">
                <h2>{t("texts.co_owner_stats_tree")}</h2>
                <div className="pinned-content">
                  <StatGrid
                    cards={[
                      {
                        label: t("texts.co_owner_invited"),
                        value: stats.total_invited,
                        color: "var(--accent)",
                      },
                      {
                        label: t("texts.co_owner_paid_users"),
                        value: stats.paid_users,
                        color: "var(--warning)",
                      },
                      {
                        label: t("texts.co_owner_max_depth"),
                        value: stats.max_depth,
                        color: "var(--text-primary)",
                      },
                      {
                        label: t("texts.co_owner_newest_join"),
                        value: stats.newest_join_date || t("texts.not_specified"),
                        color: "var(--text-secondary)",
                      },
                    ]}
                  />
                </div>
              </div>

              <div className="pinned-section fade-in delay-3">
                <h2>{t("texts.co_owner_stats_money")}</h2>
                <div className="pinned-content">
                  <StatGrid
                    cards={[
                      {
                        label: t("texts.co_owner_revenue"),
                        value: `${stats.revenue} ${t("texts.currency_rub")}`,
                        color: "var(--accent)",
                      },
                      {
                        label: t("texts.co_owner_commission"),
                        value: `${stats.commission} ${t("texts.currency_rub")}`,
                        color: "var(--success)",
                      },
                      {
                        label: t("texts.co_owner_commission_percent"),
                        value: `${stats.commission_percent}%`,
                        color: "var(--warning)",
                      },
                    ]}
                  />
                </div>
              </div>

              <div className="pinned-section fade-in delay-4">
                <h2>{t("texts.co_owner_stats_activity")}</h2>
                <div className="pinned-content">
                  <StatGrid
                    cards={[
                      {
                        label: t("texts.co_owner_active_subs"),
                        value: stats.active_subscriptions,
                        color: "var(--success)",
                      },
                      {
                        label: t("texts.co_owner_traffic"),
                        value: `${stats.traffic_gb} GB`,
                        color: "var(--accent)",
                      },
                    ]}
                  />
                </div>
              </div>
            </>
          ) : null}

          <div className="pinned-section fade-in delay-4">
            <h2>{t("texts.co_owner_payments")}</h2>
            <div className="pinned-content">
              <div className="data-table-wrap" style={{ marginTop: "16px" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("texts.co_owner_payment_id")}</th>
                      <th>{t("texts.user_id")}</th>
                      <th>{t("texts.co_owner_amount")}</th>
                      <th>{t("texts.co_owner_commission")}</th>
                      <th>{t("texts.status")}</th>
                      <th>{t("texts.co_owner_method")}</th>
                      <th>{t("texts.co_owner_date")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(payments?.payments ?? []).map((item) => (
                      <tr key={item.payment_id}>
                        <td data-label={t("texts.co_owner_payment_id")}>{item.payment_id}</td>
                        <td className="data-num" data-label={t("texts.user_id")}>
                          {item.uid}
                        </td>
                        <td className="data-num" data-label={t("texts.co_owner_amount")}>
                          {item.amount}
                        </td>
                        <td className="data-num" data-label={t("texts.co_owner_commission")}>
                          {item.commission}
                        </td>
                        <td data-label={t("texts.status")}>{item.status}</td>
                        <td data-label={t("texts.co_owner_method")}>{item.method}</td>
                        <td data-label={t("texts.co_owner_date")}>{item.timestamp}</td>
                      </tr>
                    ))}
                    {(payments?.payments.length ?? 0) === 0 && (
                      <tr>
                        <td
                          colSpan={7}
                          style={{
                            textAlign: "center",
                            color: "var(--text-secondary)",
                            padding: "24px",
                          }}
                        >
                          {t("texts.co_owner_empty")}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
