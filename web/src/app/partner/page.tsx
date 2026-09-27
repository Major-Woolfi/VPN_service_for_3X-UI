"use client";

import Header from "@/components/Header";
import Link from "next/link";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import {
  getPartnerProfile,
  getPartnerStats,
  getPartnerPublicInfo,
  getPartnerPendingStatus,
  partnerApply,
  partnerRenew,
  partnerWithdraw,
} from "@/lib/api";
import type {
  PartnerProfileResponse,
  PartnerStatsResponse,
  PartnerPublicInfoResponse,
} from "@/lib/types";
import { useLanguage } from "@/contexts/LanguageContext";
import { SafeHTML } from "@/components/SafeHTML";

export default function PartnerPage() {
  const router = useRouter();
  const { loading: authLoading, user } = useAuth();
  const isAdmin = Boolean(user?.is_admin);
  const telegramLinked = (user?.telegram_id || 0) > 0;
  const { t, tHtml } = useLanguage();
  const [profile, setProfile] = useState<PartnerProfileResponse | null>(null);
  const [stats, setStats] = useState<PartnerStatsResponse | null>(null);
  const [publicInfo, setPublicInfo] =
    useState<PartnerPublicInfoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [isPartner, setIsPartner] = useState(false);
  const [hasPendingApplication, setHasPendingApplication] = useState(false);

  const [followers, setFollowers] = useState("");
  const [socials, setSocials] = useState("");
  const [nickname, setNickname] = useState("");
  const [periodMonths, setPeriodMonths] = useState("");
  const [bonusType, setBonusType] = useState("days");
  const [bonusValue, setBonusValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);

  const [renewMonths, setRenewMonths] = useState("1");
  const [renewLoading, setRenewLoading] = useState(false);
  const [showRenewForm, setShowRenewForm] = useState(false);

  const [showWithdrawForm, setShowWithdrawForm] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawFio, setWithdrawFio] = useState("");
  const [withdrawPhone, setWithdrawPhone] = useState("");
  const [withdrawBank, setWithdrawBank] = useState("");
  const [withdrawLoading, setWithdrawLoading] = useState(false);

  const handleWithdrawSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile || !user || withdrawLoading) return;
    const amount = Number(withdrawAmount);
    if (amount <= 0) {
      setIsError(true);
      setMessage(t("texts.amount_must_be_positive"));
      return;
    }
    if (amount > Number(profile.balance || 0)) {
      setIsError(true);
      setMessage(t("texts.insufficient_balance"));
      return;
    }
    if (!withdrawFio.trim()) {
      setIsError(true);
      setMessage(t("texts.fio_required"));
      return;
    }
    if (!withdrawPhone.trim()) {
      setIsError(true);
      setMessage(t("texts.phone_required"));
      return;
    }
    if (!withdrawBank.trim()) {
      setIsError(true);
      setMessage(t("texts.bank_required"));
      return;
    }
    setWithdrawLoading(true);
    setIsError(false);
    setMessage("");
    try {
      await partnerWithdraw({
        amount,
        fio: withdrawFio.trim(),
        phone: withdrawPhone.trim(),
        bank: withdrawBank.trim(),
      });
      setMessage(t("texts.withdrawal_request_submitted"));
      setIsError(false);
      setShowWithdrawForm(false);
      setWithdrawAmount("");
      setWithdrawFio("");
      setWithdrawPhone("");
      setWithdrawBank("");
      const newProfile = await getPartnerProfile();
      setProfile(newProfile);
    } catch (e) {
      setIsError(true);
      setMessage(e instanceof Error ? e.message : t("texts.withdrawal_failed"));
    } finally {
      setWithdrawLoading(false);
    }
  };

  const handleWithdraw = async () => {
    if (!profile || !user || withdrawLoading) return;
    const balance = Number(profile.balance || 0);
    if (balance <= 0) {
      setIsError(true);
      setMessage(t("texts.insufficient_balance"));
      return;
    }
    setShowWithdrawForm(true);
    setWithdrawAmount(String(balance));
  };

  const handleRenew = () => {
    const months = Math.max(1, parseInt(renewMonths, 10) || 1);
    setRenewLoading(true);
    setIsError(false);
    setMessage("");
    partnerRenew({ months })
      .then((res) => {
        setMessage(t("texts.partner_renew_success", { months: res.months }));
        setIsError(false);
        setShowRenewForm(false);
      })
      .catch((e: unknown) => {
        setIsError(true);
        setMessage(
          e instanceof Error ? e.message : t("texts.partner_renew_error"),
        );
      })
      .finally(() => {
        setRenewLoading(false);
      });
  };

  useEffect(() => {
    if (authLoading) return;
    (async () => {
      setLoading(true);
      try {
        const [pubInfo] = await Promise.all([getPartnerPublicInfo()]);
        setPublicInfo(pubInfo);
      } catch {
        setPublicInfo(null);
      }
      if (!user) {
        setLoading(false);
        return;
      }
      try {
        const [prof, st] = await Promise.all([
          getPartnerProfile(),
          getPartnerStats(),
        ]);
        setProfile(prof);
        setStats(st);
        setIsPartner(prof.status === "active");
        setHasPendingApplication(false);
      } catch {
        setIsPartner(false);
        if (user?.pending_partner_application) {
          setHasPendingApplication(true);
        } else {
          try {
            const { has_pending_application } = await getPartnerPendingStatus();
            setHasPendingApplication(has_pending_application);
          } catch {
            setHasPendingApplication(false);
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    if (!telegramLinked) {
      setMessage(t("texts.partner_requires_telegram"));
      setIsError(true);
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      await partnerApply({
        followers: parseInt(followers, 10) || 0,
        social_links: socials,
        nickname,
        period_months: parseInt(periodMonths, 10) || 1,
        bonus_type: bonusType,
        bonus_value: parseInt(bonusValue, 10) || 0,
      });
      setMessage(t("texts.partner_apply_success"));
      setIsError(false);
      setFollowers("");
      setSocials("");
      setNickname("");
      setPeriodMonths("");
      setBonusValue("");
    } catch {
      setMessage(t("texts.partner_apply_error"));
      setIsError(true);
    } finally {
      setSubmitting(false);
    }
  };

  const renderPublicInfo = () => {
    if (!publicInfo) return null;
    const socialsList = publicInfo.required_socials
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const socialLabels: Record<string, string> = {
      telegram: t("buttons.social_telegram"),
      youtube: t("buttons.youtube"),
      tiktok: t("buttons.tiktok"),
    };
    return (
      <>
        <div className="pinned-section fade-in">
          <h2>{t("texts.partner_requirements")}</h2>
          <div className="pinned-content">
            <p style={{ marginTop: "16px", color: "var(--text-secondary)" }}>
              <SafeHTML
                html={tHtml("texts.partner_requirements_detailed", {
                  min_followers: publicInfo.min_followers,
                  min_avg_reach: publicInfo.min_avg_reach,
                  required_socials: socialsList
                    .map((s) => socialLabels[s] || s)
                    .join(", "),
                })}
              />
            </p>
          </div>
        </div>

        <div className="pinned-section fade-in delay-1">
          <h2>{t("texts.partner_conditions")}</h2>
          <div className="pinned-content">
            <p style={{ marginTop: "16px", color: "var(--text-secondary)" }}>
              <SafeHTML
                html={tHtml("texts.partner_conditions_detailed", {
                  commission_percent: publicInfo.commission_percent,
                })}
              />
            </p>
            <div style={{ marginTop: "20px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "12px",
                  paddingBottom: "12px",
                  borderBottom: "1px solid var(--border-color)",
                }}
              >
                <span style={{ color: "var(--text-secondary)" }}>
                  {t("texts.partner_commission", {
                    commission_percent: publicInfo.commission_percent,
                  })}
                </span>
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "12px",
                  paddingBottom: "12px",
                  borderBottom: "1px solid var(--border-color)",
                }}
              >
                <span style={{ color: "var(--text-secondary)" }}>
                  {t("texts.partner_payment_terms", { min_amount: 500 })}
                </span>
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "12px",
                  paddingBottom: "12px",
                  borderBottom: "1px solid var(--border-color)",
                }}
              >
                <span style={{ color: "var(--text-secondary)" }}>
                  {t("texts.partner_period", {
                    min: publicInfo.min_period_months,
                    max: publicInfo.max_period_months,
                  })}
                </span>
              </div>
            </div>
            <div
              style={{
                marginTop: "16px",
                padding: "12px",
                background: "var(--bg-tertiary)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <p
                style={{
                  fontSize: "13px",
                  color: "var(--text-secondary)",
                  lineHeight: "1.6",
                }}
              >
                {t("texts.partner_withdrawal_info")}
              </p>
            </div>
          </div>
        </div>
      </>
    );
  };

  if (authLoading || loading) {
    return (
      <>
        <Header currentPage="/partner" />
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

  if (!user) {
    return (
      <>
        <Header currentPage="/partner" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t("texts.partner_program")}</h1>
                <p className="profile-username">
                  {t("texts.partner_program_text")}
                </p>
              </div>
            </div>
            {publicInfo && renderPublicInfo()}
            <div className="pinned-section fade-in delay-2">
              <h2>{t("texts.become_partner")}</h2>
              <div className="pinned-content">
                <p
                  style={{ marginTop: "16px", color: "var(--text-secondary)" }}
                >
                  {t("texts.login_required_partner")}
                </p>
                <div
                  style={{ display: "flex", gap: "12px", marginTop: "16px" }}
                >
                  <button
                    onClick={() => router.push("/login?next=/partner")}
                    className="button"
                    style={{ flex: 1 }}
                  >
                    {t("buttons.login")}
                  </button>
                  <button
                    onClick={() => router.push("/register?next=/partner")}
                    className="button"
                    style={{
                      flex: 1,
                      background: "var(--bg-tertiary)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {t("buttons.register")}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  if (!isPartner) {
    return (
      <>
        <Header currentPage="/partner" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t("texts.partner_program")}</h1>
                <p className="profile-username">
                  {t("texts.partner_program_text")}
                </p>
              </div>
            </div>

            {hasPendingApplication ? (
              <div className="pinned-section fade-in">
                <div className="pinned-content">
                  <p
                    style={{
                      marginTop: "16px",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <SafeHTML
                      html={tHtml("texts.partner_application_pending_block")}
                    />
                  </p>
                </div>
              </div>
            ) : (
              <>
                {publicInfo && renderPublicInfo()}

                <div className="pinned-section fade-in delay-2">
                  <h2>{t("texts.become_partner")}</h2>
                  <div className="pinned-content">
                    <p
                      style={{
                        marginTop: "16px",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {t("texts.partner_apply_text")}
                    </p>
                    {!telegramLinked && (
                      <p style={{ marginTop: "16px", color: "var(--danger)" }}>
                        {t("texts.partner_requires_telegram")}{" "}
                        <Link
                          href="/settings"
                          style={{ color: "var(--accent)" }}
                        >
                          {t("buttons.link_telegram")}
                        </Link>
                      </p>
                    )}
                    {isAdmin ? (
                      <p
                        style={{
                          marginTop: "16px",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {t("texts.partner_admin_not_allowed")}
                      </p>
                    ) : (
                      <form
                        onSubmit={handleSubmit}
                        style={{
                          marginTop: "20px",
                          display: "flex",
                          flexDirection: "column",
                          gap: "12px",
                        }}
                      >
                        <div className="number-input-wrapper">
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() =>
                              setFollowers(
                                String(
                                  Math.max(
                                    publicInfo?.min_followers || 1,
                                    (parseInt(followers, 10) || 0) - 1,
                                  ),
                                ),
                              )
                            }
                          >
                            −
                          </button>
                          <input
                            type="number"
                            value={followers}
                            onChange={(e) => setFollowers(e.target.value)}
                            placeholder={t("texts.partner_followers")}
                            required
                            min={publicInfo?.min_followers || 1}
                          />
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() =>
                              setFollowers(
                                String((parseInt(followers, 10) || 0) + 1),
                              )
                            }
                          >
                            +
                          </button>
                        </div>
                        <input
                          type="text"
                          value={socials}
                          onChange={(e) => setSocials(e.target.value)}
                          placeholder={t(
                            "texts.partner_apply_socials_placeholder",
                          )}
                          className="form-input"
                          required
                        />
                        <input
                          type="text"
                          value={nickname}
                          onChange={(e) => setNickname(e.target.value)}
                          placeholder={t("texts.partner_nickname")}
                          className="form-input"
                          required
                        />
                        <div className="number-input-wrapper">
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() =>
                              setPeriodMonths(
                                String(
                                  Math.max(
                                    publicInfo?.min_period_months || 1,
                                    (parseInt(periodMonths, 10) || 0) - 1,
                                  ),
                                ),
                              )
                            }
                          >
                            −
                          </button>
                          <input
                            type="number"
                            value={periodMonths}
                            onChange={(e) => setPeriodMonths(e.target.value)}
                            placeholder={t("texts.partner_period_label", {
                              min: publicInfo?.min_period_months || 1,
                              max: publicInfo?.max_period_months || 12,
                            })}
                            required
                            min={publicInfo?.min_period_months || 1}
                            max={publicInfo?.max_period_months || 12}
                          />
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() =>
                              setPeriodMonths(
                                String(
                                  Math.min(
                                    publicInfo?.max_period_months || 12,
                                    (parseInt(periodMonths, 10) || 0) + 1,
                                  ),
                                ),
                              )
                            }
                          >
                            +
                          </button>
                        </div>
                        <select
                          value={bonusType}
                          onChange={(e) => {
                            setBonusType(e.target.value);
                            setBonusValue("");
                          }}
                          className="form-input"
                          style={{ marginBottom: "0" }}
                        >
                          <option value="days">
                            {t("texts.partner_bonus_days", {
                              min: publicInfo?.bonus_days_min || 0,
                              max: publicInfo?.bonus_days_max || 0,
                            })}
                          </option>
                          <option value="trust">
                            {t("texts.partner_trust_points", {
                              min: publicInfo?.trust_points_min || 0,
                              max: publicInfo?.trust_points_max || 0,
                            })}
                          </option>
                        </select>
                        <div className="number-input-wrapper">
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              const min =
                                bonusType === "days"
                                  ? publicInfo?.bonus_days_min || 0
                                  : publicInfo?.trust_points_min || 0;
                              setBonusValue(
                                String(
                                  Math.max(
                                    min,
                                    (parseInt(bonusValue, 10) || 0) - 1,
                                  ),
                                ),
                              );
                            }}
                          >
                            −
                          </button>
                          <input
                            type="number"
                            value={bonusValue}
                            onChange={(e) => setBonusValue(e.target.value)}
                            placeholder={
                              bonusType === "days"
                                ? t("texts.partner_trust_placeholder", {
                                    min: publicInfo?.bonus_days_min || 0,
                                    max: publicInfo?.bonus_days_max || 0,
                                  })
                                : t("texts.partner_trust_placeholder", {
                                    min: publicInfo?.trust_points_min || 0,
                                    max: publicInfo?.trust_points_max || 0,
                                  })
                            }
                            required
                            min={
                              bonusType === "days"
                                ? publicInfo?.bonus_days_min || 0
                                : publicInfo?.trust_points_min || 0
                            }
                            max={
                              bonusType === "days"
                                ? publicInfo?.bonus_days_max || 0
                                : publicInfo?.trust_points_max || 0
                            }
                          />
                          <button
                            type="button"
                            className="number-btn"
                            onClick={() => {
                              const max =
                                bonusType === "days"
                                  ? publicInfo?.bonus_days_max || 0
                                  : publicInfo?.trust_points_max || 0;
                              setBonusValue(
                                String(
                                  Math.min(
                                    max,
                                    (parseInt(bonusValue, 10) || 0) + 1,
                                  ),
                                ),
                              );
                            }}
                          >
                            +
                          </button>
                        </div>
                        {message && (
                          <div
                            style={{
                              padding: "12px",
                              borderRadius: "var(--radius-sm)",
                              fontSize: "14px",
                              background: isError
                                ? "rgba(255,0,0,0.1)"
                                : "var(--accent-glow)",
                              color: isError
                                ? "var(--danger)"
                                : "var(--accent)",
                              border: `1px solid ${isError ? "var(--danger)" : "var(--accent)"}`,
                            }}
                          >
                            {message}
                          </div>
                        )}
                        <button
                          type="submit"
                          className="button"
                          style={{ width: "100%" }}
                          disabled={submitting || !telegramLinked}
                        >
                          {submitting
                            ? t("texts.waiting")
                            : t("texts.partner_apply_submit")}
                        </button>
                      </form>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Header currentPage="/partner" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.partner_dashboard")}</h1>
              <p className="profile-username">
                {t("texts.partner_dashboard_subtitle")}
              </p>
            </div>
          </div>

          {profile && (
            <div className="pinned-section fade-in">
              <h2>{t("texts.partner_dashboard")}</h2>
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
                      {t("texts.username")}
                    </span>
                    <span>{profile.ref_link_code}</span>
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
                      {t("texts.status")}
                    </span>
                    <span
                      style={{
                        color:
                          profile.status === "active"
                            ? "var(--success)"
                            : "var(--warning)",
                      }}
                    >
                      {profile.status === "active"
                        ? t("texts.status_active")
                        : t("texts.pending")}
                    </span>
                  </div>
                  <div
                    style={{ display: "flex", justifyContent: "space-between" }}
                  >
                    <span style={{ color: "var(--text-secondary)" }}>
                      {t("texts.referral_link")}
                    </span>
                    {profile?.ref_link ? (
                      <a
                        href={profile.ref_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          color: "var(--accent)",
                          wordBreak: "break-all",
                        }}
                      >
                        {profile.ref_link}
                      </a>
                    ) : (
                      <span style={{ color: "var(--text-secondary)" }}>
                        {profile?.ref_link_code || t("texts.not_specified")}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {stats && (
            <div className="pinned-section fade-in delay-1">
              <h2>{t("texts.stats")}</h2>
              <div className="pinned-content">
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                    gap: "16px",
                    marginTop: "16px",
                  }}
                >
                  <div
                    style={{
                      padding: "20px",
                      background: "var(--bg-tertiary)",
                      borderRadius: "var(--radius-md)",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "28px",
                        fontWeight: "700",
                        color: "var(--accent)",
                      }}
                    >
                      {stats.total_refs || 0}
                    </div>
                    <div
                      style={{
                        fontSize: "14px",
                        color: "var(--text-secondary)",
                        marginTop: "8px",
                      }}
                    >
                      {t("texts.total_refs")}
                    </div>
                  </div>
                  <div
                    style={{
                      padding: "20px",
                      background: "var(--bg-tertiary)",
                      borderRadius: "var(--radius-md)",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "28px",
                        fontWeight: "700",
                        color: "var(--success)",
                      }}
                    >
                      {stats.paid_refs || 0}
                    </div>
                    <div
                      style={{
                        fontSize: "14px",
                        color: "var(--text-secondary)",
                        marginTop: "8px",
                      }}
                    >
                      {t("texts.paid_refs")}
                    </div>
                  </div>
                  <div
                    style={{
                      padding: "20px",
                      background: "var(--bg-tertiary)",
                      borderRadius: "var(--radius-md)",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "28px",
                        fontWeight: "700",
                        color: "var(--warning)",
                      }}
                    >
                      {stats.commission_total || 0} {t("texts.currency_rub")}
                    </div>
                    <div
                      style={{
                        fontSize: "14px",
                        color: "var(--text-secondary)",
                        marginTop: "8px",
                      }}
                    >
                      {t("texts.total_earned")}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="pinned-section fade-in delay-2">
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
                <button
                  className="button"
                  style={{ width: "100%" }}
                  onClick={handleWithdraw}
                  disabled={withdrawLoading || showWithdrawForm}
                >
                  {withdrawLoading ? t("texts.loading") : t("buttons.withdraw")}
                </button>
                <button
                  className="button"
                  style={{ width: "100%" }}
                  onClick={() => {
                    setRenewMonths(
                      String(user?.mate_period_months || 1),
                    );
                    setMessage("");
                    setIsError(false);
                    setShowRenewForm((prev) => !prev);
                  }}
                  disabled={renewLoading || !telegramLinked}
                >
                  {t("buttons.renew_partner")}
                </button>
                {message && !showRenewForm && (
                  <div
                    style={{
                      padding: "12px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "14px",
                      background: isError
                        ? "rgba(255,0,0,0.1)"
                        : "var(--accent-glow)",
                      color: isError ? "var(--danger)" : "var(--accent)",
                      border: `1px solid ${isError ? "var(--danger)" : "var(--accent)"}`,
                    }}
                  >
                    {message}
                  </div>
                )}
              </div>
            </div>
          </div>

          {showRenewForm && (
            <div className="pinned-section fade-in">
              <h2>{t("buttons.renew_partner")}</h2>
              <div className="pinned-content">
                <div
                  style={{
                    marginTop: "16px",
                    padding: "12px",
                    background: "var(--bg-tertiary)",
                    borderRadius: "var(--radius-sm)",
                    marginBottom: "16px",
                  }}
                >
                  <p
                    style={{
                      fontSize: "13px",
                      color: "var(--text-secondary)",
                      lineHeight: "1.6",
                    }}
                  >
                    {t("texts.partner_renew_free_info")}
                  </p>
                </div>
                <div
                  className="number-input-wrapper"
                  style={{ marginBottom: "12px" }}
                >
                  <button
                    type="button"
                    className="number-btn"
                    onClick={() =>
                      setRenewMonths(
                        String(Math.max(1, (parseInt(renewMonths, 10) || 1) - 1)),
                      )
                    }
                  >
                    −
                  </button>
                  <input
                    type="number"
                    value={renewMonths}
                    min="1"
                    max={publicInfo?.max_period_months || 12}
                    onChange={(e) => setRenewMonths(e.target.value)}
                    placeholder={t("texts.partner_period_label", {
                      min: 1,
                      max: publicInfo?.max_period_months || 12,
                    })}
                    required
                  />
                  <button
                    type="button"
                    className="number-btn"
                    onClick={() =>
                      setRenewMonths(
                        String(
                          Math.min(
                            publicInfo?.max_period_months || 12,
                            (parseInt(renewMonths, 10) || 1) + 1,
                          ),
                        ),
                      )
                    }
                  >
                    +
                  </button>
                </div>
                {message && (
                  <div
                    style={{
                      marginBottom: "12px",
                      padding: "12px",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "14px",
                      background: isError
                        ? "rgba(255,0,0,0.1)"
                        : "var(--accent-glow)",
                      color: isError ? "var(--danger)" : "var(--accent)",
                      border: `1px solid ${isError ? "var(--danger)" : "var(--accent)"}`,
                    }}
                  >
                    {message}
                  </div>
                )}
                <div style={{ display: "flex", gap: "12px" }}>
                  <button
                    type="button"
                    onClick={() => setShowRenewForm(false)}
                    className="button"
                    style={{ flex: 1, background: "var(--bg-tertiary)" }}
                  >
                    {t("buttons.cancel")}
                  </button>
                  <button
                    onClick={handleRenew}
                    className="button"
                    style={{ flex: 1 }}
                    disabled={renewLoading}
                  >
                    {renewLoading ? t("texts.waiting") : t("buttons.confirm")}
                  </button>
                </div>
              </div>
            </div>
          )}

          {showWithdrawForm && (
            <div className="pinned-section fade-in">
              <h2>{t("texts.withdrawal_request")}</h2>
              <div className="pinned-content">
                <div
                  style={{
                    marginTop: "16px",
                    padding: "12px",
                    background: "var(--bg-tertiary)",
                    borderRadius: "var(--radius-sm)",
                    marginBottom: "16px",
                  }}
                >
                  <p
                    style={{
                      fontSize: "13px",
                      color: "var(--text-secondary)",
                      lineHeight: "1.6",
                    }}
                  >
                    {t("texts.withdrawal_sbps_info")}
                  </p>
                </div>
                <form
                  onSubmit={handleWithdrawSubmit}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  <div>
                    <label
                      style={{
                        fontSize: "12px",
                        color: "var(--text-secondary)",
                        marginBottom: "4px",
                        display: "block",
                      }}
                    >
                      {t("texts.withdrawal_amount")}
                    </label>
                    <input
                      type="number"
                      value={withdrawAmount}
                      onChange={(e) => setWithdrawAmount(e.target.value)}
                      placeholder={t("texts.withdrawal_amount_placeholder", {
                        balance: profile?.balance || 0,
                      })}
                      className="form-input"
                      required
                      min="1"
                      max={profile?.balance || 0}
                      step="0.01"
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        fontSize: "12px",
                        color: "var(--text-secondary)",
                        marginBottom: "4px",
                        display: "block",
                      }}
                    >
                      {t("texts.withdrawal_fio")}
                    </label>
                    <input
                      type="text"
                      value={withdrawFio}
                      onChange={(e) => setWithdrawFio(e.target.value)}
                      placeholder={t("texts.withdrawal_fio_placeholder")}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        fontSize: "12px",
                        color: "var(--text-secondary)",
                        marginBottom: "4px",
                        display: "block",
                      }}
                    >
                      {t("texts.withdrawal_phone")}
                    </label>
                    <input
                      type="tel"
                      value={withdrawPhone}
                      onChange={(e) => setWithdrawPhone(e.target.value)}
                      placeholder={t("texts.withdrawal_phone_placeholder")}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        fontSize: "12px",
                        color: "var(--text-secondary)",
                        marginBottom: "4px",
                        display: "block",
                      }}
                    >
                      {t("texts.withdrawal_bank")}
                    </label>
                    <input
                      type="text"
                      value={withdrawBank}
                      onChange={(e) => setWithdrawBank(e.target.value)}
                      placeholder={t("texts.withdrawal_bank_placeholder")}
                      className="form-input"
                      required
                    />
                  </div>
                  {message && (
                    <div
                      style={{
                        padding: "12px",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "14px",
                        background: isError
                          ? "rgba(255,0,0,0.1)"
                          : "var(--accent-glow)",
                        color: isError ? "var(--danger)" : "var(--accent)",
                        border: `1px solid ${isError ? "var(--danger)" : "var(--accent)"}`,
                      }}
                    >
                      {message}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: "12px" }}>
                    <button
                      type="button"
                      className="button"
                      style={{ flex: 1, background: "var(--bg-tertiary)" }}
                      onClick={() => setShowWithdrawForm(false)}
                    >
                      {t("buttons.cancel")}
                    </button>
                    <button
                      type="submit"
                      className="button"
                      style={{ flex: 1 }}
                      disabled={withdrawLoading}
                    >
                      {withdrawLoading
                        ? t("texts.loading")
                        : t("buttons.confirm")}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
