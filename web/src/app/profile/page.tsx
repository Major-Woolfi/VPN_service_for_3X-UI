"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import { CopyableUrl } from "@/components/CopyableUrl";
import { useCopyToClipboard } from "@/app/hooks/useCopyToClipboard";
import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { getSubscriptionLink, getTariffs, renewSubscription } from "@/lib/api";
import { getErrorMessage } from "@/lib/error";
import type { SubscriptionlinkResponse, SubscriptionPaymentRequest, Tariff } from "@/lib/types";
import { ProfileHeader, ProfileRenewForm, ProfileActions } from "@/app/profile/components";

const WEB_RENEW_EXCLUDED_PLAN_IDS = new Set(["partner", "co_owner", "custom"]);

export default function ProfilePage() {
  const { user, loading: authLoading, refreshUser } = useAuth();
  const { t, lang } = useLanguage();
  const router = useRouter();
  const [fetchedSublink, setFetchedSublink] = useState<{
    key: string;
    link: SubscriptionlinkResponse | null;
  } | null>(null);
  const { copy, copied } = useCopyToClipboard();
  const [renewLoading, setRenewLoading] = useState(false);
  const [renewResult, setRenewResult] = useState<SubscriptionPaymentRequest | null>(null);
  const [renewError, setRenewError] = useState("");
  const [tariffs, setTariffs] = useState<Tariff[]>([]);

  const hasAdminSub = Boolean(user?.is_admin && user?.admin_subscription?.url);
  const needsSublinkFetch =
    Boolean(user) && !hasAdminSub && user?.subscription?.status === "active";

  const sublinkkey = `${user?.user_id ?? ""}:${user?.subscription?.plan_id ?? ""}`;

  const renewablePlanIds = useMemo(
    () => new Set(tariffs.filter((tariff) => tariff.active && !tariff.is_trial).map((t) => t.id)),
    [tariffs],
  );

  const isWebRenewablePlan = useCallback(
    (planId: string) =>
      Boolean(planId) &&
      !user?.is_admin &&
      !WEB_RENEW_EXCLUDED_PLAN_IDS.has(planId) &&
      renewablePlanIds.has(planId),
    [user?.is_admin, renewablePlanIds],
  );

  useEffect(() => {
    getTariffs()
      .then((data) => setTariffs(data.tariffs))
      .catch(() => setTariffs([]));
  }, []);

  const handleRenew = useCallback(async () => {
    if (!user) return;
    const plan = user.subscription?.plan_id || "";
    if (!isWebRenewablePlan(plan)) {
      setRenewError(t("texts.renew_unavailable_for_plan"));
      return;
    }
    setRenewLoading(true);
    setRenewError("");
    try {
      const result = await renewSubscription({ plan_id: plan });
      setRenewResult(result);
      await refreshUser();
    } catch (err) {
      setRenewError(getErrorMessage(err));
    } finally {
      setRenewLoading(false);
    }
  }, [user, refreshUser, isWebRenewablePlan, t]);

  useEffect(() => {
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent("/profile")}`);
      return;
    }
    if (!needsSublinkFetch) return;
    const aborter = new AbortController();
    getSubscriptionLink(aborter.signal)
      .then((link) => setFetchedSublink({ key: sublinkkey, link }))
      .catch(() => setFetchedSublink({ key: sublinkkey, link: null }));
    return () => aborter.abort();
  }, [user, router, needsSublinkFetch, sublinkkey]);

  const sub = user?.subscription;
  const isSubscribed = sub?.status === "active";
  const isAdminSub = hasAdminSub && !isSubscribed;
  const canRenewWeb = isSubscribed && isWebRenewablePlan(sub?.plan_id || "");

  const trafficUsed = sub?.used_gb || 0;
  const trafficTotal = sub?.traffic_gb || 0;
  const trafficPercent = trafficTotal > 0 ? Math.round((trafficUsed / trafficTotal) * 100) : 0;
  const expiryDate = sub?.expiry_sub_datatime || "";
  const formattedExpiry = expiryDate ? new Date(expiryDate).toLocaleDateString(lang) : "-";
  const planText = isAdminSub ? t("texts.admin_plan") : sub?.plan_text || "-";
  const displayTrafficTotal =
    isAdminSub || trafficTotal === 0
      ? t("texts.unlimited")
      : t("texts.traffic_gb", { value: trafficTotal });
  const displayIps = isAdminSub || !sub?.ip_limit ? t("texts.unlimited") : sub.ip_limit;

  const hasSublink = Boolean(
    fetchedSublink?.link?.vpn_url ||
    fetchedSublink?.link?.json_vpn_url ||
    user?.partner_subscription?.url ||
    user?.partner_subscription?.json_url,
  );

  const vpnUrl = fetchedSublink?.link?.vpn_url ?? "";
  const jsonVpnUrl = fetchedSublink?.link?.json_vpn_url ?? "";
  const adminTestVpnUrl = user?.admin_test_subscription?.url ?? "";
  const adminTestJsonUrl = user?.admin_test_subscription?.json_url ?? "";
  const partnerVpnUrl = user?.partner_subscription?.url ?? "";
  const partnerJsonUrl = user?.partner_subscription?.json_url ?? "";

  if (authLoading || !user) {
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

  return (
    <>
      <Header currentPage="/profile" />
      <main>
        <div className="profile">
          <ProfileHeader user={user} t={t} />

          <div className="pinned-section fade-in">
            <h2>{t("texts.subscription_status")}</h2>
            <div className="pinned-content">
              <div
                style={{
                  marginTop: "16px",
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "16px",
                  paddingBottom: "16px",
                  borderBottom: "1px solid var(--border-color)",
                }}
              >
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.status")}</span>
                <span
                  style={{
                    color: isSubscribed || hasAdminSub ? "var(--success)" : "var(--text-secondary)",
                    fontWeight: "600",
                  }}
                >
                  {isSubscribed || hasAdminSub
                    ? t("texts.status_active")
                    : t("texts.no_subscription")}
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
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.plan")}</span>
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
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.expires")}</span>
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
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.traffic")}</span>
                <span>
                  {t("texts.traffic_gb", { value: trafficUsed })} / {displayTrafficTotal}
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
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.ips")}</span>
                <span>{displayIps}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.trust_score")}</span>
                <span>
                  {user?.trust_score || 0} ({user?.discount_percent || 0}% {t("texts.discount")})
                </span>
              </div>
            </div>
          </div>

          {!isSubscribed && !hasAdminSub ? (
            <div className="pinned-section fade-in">
              <h2>{t("buttons.buy")}</h2>
              <div className="pinned-content">
                <p style={{ marginTop: "16px", color: "var(--text-secondary)" }}>
                  {t("texts.no_subscription_text")}
                </p>
                <Link href="/subscribe" className="button" style={{ marginTop: "16px" }}>
                  {t("buttons.buy")}
                </Link>
              </div>
            </div>
          ) : canRenewWeb ? (
            <>
              <ProfileRenewForm
                user={user}
                renewLoading={renewLoading}
                renewResult={renewResult}
                renewError={renewError}
                handleRenew={handleRenew}
                t={t}
              />

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
                      style={{ marginTop: "8px", fontSize: "14px", color: "var(--text-secondary)" }}
                    >
                      {trafficTotal === 0
                        ? t("texts.unlimited")
                        : t("texts.traffic_used", { percent: trafficPercent, total: trafficTotal })}
                    </p>
                  </div>
                </div>
              </div>

              {(isSubscribed || (user?.is_admin && user?.admin_subscription?.url)) &&
                hasSublink && (
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
                        {vpnUrl ? (
                          <CopyableUrl
                            url={vpnUrl}
                            copied={copied === "vpn"}
                            onCopy={() => copy(vpnUrl)}
                          />
                        ) : null}
                        {jsonVpnUrl ? (
                          <CopyableUrl
                            url={jsonVpnUrl}
                            copied={copied === "json"}
                            onCopy={() => copy(jsonVpnUrl)}
                          />
                        ) : null}
                      </div>
                    </div>
                  </div>
                )}

              {user?.is_admin &&
                (user.admin_test_subscription?.url || user.admin_test_subscription?.json_url) && (
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
                        {adminTestVpnUrl ? (
                          <CopyableUrl
                            url={adminTestVpnUrl}
                            copied={copied === "admin-test-vpn"}
                            onCopy={() => copy(adminTestVpnUrl)}
                          />
                        ) : null}
                        {adminTestJsonUrl ? (
                          <CopyableUrl
                            url={adminTestJsonUrl}
                            copied={copied === "admin-test-json"}
                            onCopy={() => copy(adminTestJsonUrl)}
                          />
                        ) : null}
                      </div>
                    </div>
                  </div>
                )}

              {user?.is_partner &&
                (user.partner_subscription?.url || user.partner_subscription?.json_url) && (
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
                        {partnerVpnUrl ? (
                          <CopyableUrl
                            url={partnerVpnUrl}
                            copied={copied === "partner-vpn"}
                            onCopy={() => copy(partnerVpnUrl)}
                          />
                        ) : null}
                        {partnerJsonUrl ? (
                          <CopyableUrl
                            url={partnerJsonUrl}
                            copied={copied === "partner-json"}
                            onCopy={() => copy(partnerJsonUrl)}
                          />
                        ) : null}
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span style={{ color: "var(--text-secondary)" }}>
                            {t("texts.traffic")}
                          </span>
                          <span>
                            {t("texts.traffic_gb", {
                              value: user.partner_subscription?.used_gb ?? 0,
                            })}{" "}
                            /{" "}
                            {!user.partner_subscription?.traffic_gb
                              ? t("texts.unlimited")
                              : t("texts.traffic_gb", {
                                  value: user.partner_subscription.traffic_gb,
                                })}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              <ProfileActions
                isSubscribed={isSubscribed}
                hasAdminSub={hasAdminSub}
                user={user}
                t={t}
              />
            </>
          ) : (
            <div className="pinned-section fade-in">
              <h2>{t("buttons.renew_subscription")}</h2>
              <div className="pinned-content">
                <p style={{ marginTop: "16px", color: "var(--text-secondary)" }}>
                  {t("texts.renew_unavailable_for_plan")}
                </p>
                <Link href="/subscribe" className="button" style={{ marginTop: "16px" }}>
                  {t("buttons.buy")}
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
