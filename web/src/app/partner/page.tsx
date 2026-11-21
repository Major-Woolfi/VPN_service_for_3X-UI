"use client";

import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import { StatGrid } from "@/components/StatGrid";
import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import {
  getPartnerProfile,
  getPartnerStats,
  getPartnerPublicInfo,
  partnerApply,
  partnerRenew,
} from "@/lib/api";
import { getErrorMessage } from "@/lib/error";
import type {
  PartnerProfileResponse,
  PartnerStatsResponse,
  PartnerPublicInfoResponse,
} from "@/lib/types";

export default function PartnerPage() {
  const { user, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();

  const [profile, setProfile] = useState<PartnerProfileResponse | null>(null);
  const [stats, setStats] = useState<PartnerStatsResponse | null>(null);
  const [publicInfo, setPublicInfo] = useState<PartnerPublicInfoResponse | null>(null);
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [followers, setFollowers] = useState("");
  const [socials, setSocials] = useState("");
  const [nickname, setNickname] = useState("");
  const [periodMonths, setPeriodMonths] = useState("");
  const [bonusType, setBonusType] = useState("days");
  const [bonusValue, setBonusValue] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pi = await getPartnerPublicInfo();
        if (!cancelled) setPublicInfo(pi);
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!user?.is_partner) {
      setProfile(null);
      setStats(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [p, s] = await Promise.all([getPartnerProfile(), getPartnerStats()]);
        if (!cancelled) {
          setProfile(p);
          setStats(s);
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, [user?.is_partner]);

  const isPartner = Boolean(user?.is_partner);
  const isPending = Boolean(user?.pending_partner_application);
  const telegramLinked = Boolean(user?.telegram_id);
  const minPeriod = publicInfo?.min_period_months || 1;
  const maxPeriod = publicInfo?.max_period_months || 12;
  const minFollowers = publicInfo?.min_followers || 0;
  const bonusMin =
    bonusType === "trust" ? publicInfo?.trust_points_min || 0 : publicInfo?.bonus_days_min || 0;
  const bonusMax =
    bonusType === "trust" ? publicInfo?.trust_points_max || 0 : publicInfo?.bonus_days_max || 0;

  const stepNumber = (value: string, delta: number, min: number, max: number) => {
    const current = parseInt(value, 10);
    const base = Number.isFinite(current) ? current : min;
    return String(Math.min(max, Math.max(min, base + delta)));
  };

  const handleApply = async () => {
    if (!telegramLinked) {
      setMessage(t("texts.partner_requires_telegram"));
      setIsError(true);
      return;
    }
    const followersValue = parseInt(followers, 10);
    const periodValue = parseInt(periodMonths, 10);
    const bonusValueNumber = parseInt(bonusValue, 10);
    if (!Number.isFinite(followersValue) || followersValue < minFollowers) {
      setMessage(t("texts.partner_req_followers", { count: minFollowers }));
      setIsError(true);
      return;
    }
    if (!Number.isFinite(periodValue) || periodValue < minPeriod || periodValue > maxPeriod) {
      setMessage(t("texts.partner_period_label", { min: minPeriod, max: maxPeriod }));
      setIsError(true);
      return;
    }
    if (
      !Number.isFinite(bonusValueNumber) ||
      bonusValueNumber < bonusMin ||
      bonusValueNumber > bonusMax
    ) {
      setMessage(t("texts.partner_trust_placeholder", { min: bonusMin, max: bonusMax }));
      setIsError(true);
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      await partnerApply({
        followers: followersValue,
        social_links: socials.trim(),
        nickname: nickname.trim(),
        period_months: periodValue,
        bonus_type: bonusType,
        bonus_value: bonusValueNumber,
      });
      setMessage(t("texts.partner_apply_success"));
      setIsError(false);
    } catch (err) {
      setMessage(getErrorMessage(err));
      setIsError(true);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRenew = async () => {
    if (!telegramLinked) {
      setMessage(t("texts.partner_requires_telegram"));
      setIsError(true);
      return;
    }
    const months = parseInt(periodMonths, 10);
    const value = Number.isFinite(months) ? months : minPeriod;
    setMessage("");
    try {
      await partnerRenew({ months: value });
      setMessage(t("texts.partner_renew_success", { months: value }));
      setIsError(false);
    } catch (err) {
      setMessage(getErrorMessage(err));
      setIsError(true);
    }
  };

  const messageBlock = message ? (
    <div
      className={`${isError ? "error-message" : "success-message"} form-grid-wide`}
      style={{ marginTop: "12px" }}
    >
      {message}
    </div>
  ) : null;

  if (authLoading || !user) {
    return (
      <>
        <Header currentPage="/partner" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t("texts.partner_program")}</h1>
                <p className="profile-username">{t("texts.partner_program_text")}</p>
              </div>
            </div>
            <div className="pinned-section fade-in">
              <div className="pinned-content">
                <p className="text-secondary" style={{ marginTop: "16px" }}>
                  {t("texts.login_required_partner")}
                </p>
                <div className="button-pair" style={{ marginTop: "16px" }}>
                  <button onClick={() => router.push("/login?next=/partner")} className="button">
                    {t("buttons.login")}
                  </button>
                  <button
                    onClick={() => router.push("/register?next=/partner")}
                    className="button"
                    style={{ background: "var(--bg-tertiary)", color: "var(--text-primary)" }}
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
                <p className="profile-username">{t("texts.partner_program_text")}</p>
              </div>
            </div>

            <div className="pinned-section fade-in">
              <h2>{t("texts.partner_requirements")}</h2>
              <div className="pinned-content">
                <p className="text-secondary" style={{ marginTop: "16px" }}>
                  {t("texts.partner_apply_text")}
                </p>
                <p className="text-secondary" style={{ fontSize: "14px" }}>
                  {t("texts.partner_commission", {
                    commission_percent: publicInfo?.commission_percent || 0,
                  })}
                </p>
                <p className="text-secondary" style={{ fontSize: "14px" }}>
                  {t("texts.partner_req_followers", { count: minFollowers })}
                </p>
              </div>
            </div>

            <div className="pinned-section fade-in delay-1">
              <h2>{t("texts.partner_apply_submit")}</h2>
              <div className="pinned-content">
                {isPending ? (
                  <p className="text-secondary" style={{ marginTop: "16px" }}>
                    {t("texts.pending")}
                  </p>
                ) : (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void handleApply();
                    }}
                    className="form-grid"
                    style={{ marginTop: "16px" }}
                  >
                    <div className="field-label">
                      <span>{t("texts.partner_followers")}</span>
                      <span className="number-input-wrapper">
                        <button
                          type="button"
                          className="number-btn"
                          onClick={() =>
                            setFollowers(stepNumber(followers, -1, minFollowers, 1000000))
                          }
                        >
                          −
                        </button>
                        <input
                          type="number"
                          aria-label={t("texts.partner_followers")}
                          value={followers}
                          onChange={(e) => setFollowers(e.target.value)}
                          placeholder={String(minFollowers)}
                          required
                          min={minFollowers}
                        />
                        <button
                          type="button"
                          className="number-btn"
                          onClick={() =>
                            setFollowers(stepNumber(followers, 1, minFollowers, 1000000))
                          }
                        >
                          +
                        </button>
                      </span>
                    </div>
                    <div className="field-label">
                      <span>
                        {t("texts.partner_period_label", { min: minPeriod, max: maxPeriod })}
                      </span>
                      <span className="number-input-wrapper">
                        <button
                          type="button"
                          className="number-btn"
                          onClick={() =>
                            setPeriodMonths(stepNumber(periodMonths, -1, minPeriod, maxPeriod))
                          }
                        >
                          −
                        </button>
                        <input
                          type="number"
                          aria-label={t("texts.partner_period_label", {
                            min: minPeriod,
                            max: maxPeriod,
                          })}
                          value={periodMonths}
                          onChange={(e) => setPeriodMonths(e.target.value)}
                          required
                          min={minPeriod}
                          max={maxPeriod}
                        />
                        <button
                          type="button"
                          className="number-btn"
                          onClick={() =>
                            setPeriodMonths(stepNumber(periodMonths, 1, minPeriod, maxPeriod))
                          }
                        >
                          +
                        </button>
                      </span>
                    </div>
                    <div className="field-label">
                      <span>
                        {t("texts.partner_bonus_days", {
                          min: publicInfo?.bonus_days_min || 0,
                          max: publicInfo?.bonus_days_max || 0,
                        })}
                      </span>
                      <select
                        aria-label={t("texts.partner_bonus_days", {
                          min: publicInfo?.bonus_days_min || 0,
                          max: publicInfo?.bonus_days_max || 0,
                        })}
                        value={bonusType}
                        onChange={(e) => {
                          setBonusType(e.target.value);
                          setBonusValue("");
                        }}
                        className="form-input"
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
                    </div>
                    <div className="field-label">
                      <span>
                        {t("texts.partner_trust_placeholder", { min: bonusMin, max: bonusMax })}
                      </span>
                      <span className="number-input-wrapper">
                        <button
                          type="button"
                          className="number-btn"
                          onClick={() =>
                            setBonusValue(stepNumber(bonusValue, -1, bonusMin, bonusMax))
                          }
                        >
                          −
                        </button>
                        <input
                          type="number"
                          aria-label={t("texts.partner_trust_placeholder", {
                            min: bonusMin,
                            max: bonusMax,
                          })}
                          value={bonusValue}
                          onChange={(e) => setBonusValue(e.target.value)}
                          required
                          min={bonusMin}
                          max={bonusMax}
                        />
                        <button
                          type="button"
                          className="number-btn"
                          onClick={() =>
                            setBonusValue(stepNumber(bonusValue, 1, bonusMin, bonusMax))
                          }
                        >
                          +
                        </button>
                      </span>
                    </div>
                    <div className="field-label form-grid-wide">
                      <span>{t("texts.partner_apply_socials_placeholder")}</span>
                      <input
                        type="text"
                        aria-label={t("texts.partner_apply_socials_placeholder")}
                        value={socials}
                        onChange={(e) => setSocials(e.target.value)}
                        placeholder={t("texts.partner_apply_socials_placeholder")}
                        className="form-input"
                        required
                      />
                    </div>
                    <div className="field-label form-grid-wide">
                      <span>{t("texts.partner_nickname")}</span>
                      <input
                        type="text"
                        aria-label={t("texts.partner_nickname")}
                        value={nickname}
                        onChange={(e) => setNickname(e.target.value)}
                        placeholder={t("texts.partner_nickname")}
                        className="form-input"
                        required
                        pattern="[a-zA-Z0-9_]+"
                      />
                    </div>
                    {!telegramLinked && (
                      <div className="error-message form-grid-wide" style={{ margin: 0 }}>
                        {t("texts.partner_requires_telegram")}{" "}
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => router.push("/settings")}
                        >
                          {t("buttons.link_telegram")}
                        </button>
                      </div>
                    )}
                    {messageBlock}
                    <button
                      type="submit"
                      className="button form-grid-wide"
                      disabled={submitting || !telegramLinked}
                    >
                      {submitting ? t("texts.waiting") : t("texts.partner_apply_submit")}
                    </button>
                  </form>
                )}
              </div>
            </div>
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
              <p className="profile-username">{t("texts.partner_dashboard_subtitle")}</p>
            </div>
          </div>

          {profile ? (
            <div className="pinned-section fade-in">
              <h2>{t("texts.partner_program")}</h2>
              <div className="pinned-content">
                <div style={{ marginTop: "16px" }}>
                  <div className="dashboard-row">
                    <span className="text-secondary">{t("texts.web_login")}</span>
                    <span>{profile.ref_link_code}</span>
                  </div>
                  <div className="dashboard-row">
                    <span className="text-secondary">{t("texts.status")}</span>
                    <span
                      style={{
                        color: profile.status === "active" ? "var(--success)" : "var(--warning)",
                      }}
                    >
                      {profile.status === "active" ? t("texts.status_active") : t("texts.pending")}
                    </span>
                  </div>
                  <div className="dashboard-row">
                    <span className="text-secondary">{t("texts.referral_link")}</span>
                    {profile.ref_link ? (
                      <a
                        className="referral-link"
                        href={profile.ref_link}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {profile.ref_link}
                      </a>
                    ) : (
                      <span style={{ color: "var(--text-secondary)" }}>
                        {profile.ref_link_code || t("texts.not_specified")}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {stats ? (
            <div className="pinned-section fade-in delay-1">
              <h2>{t("texts.stats")}</h2>
              <div className="pinned-content">
                <StatGrid
                  cards={[
                    {
                      label: t("texts.total_refs"),
                      value: stats.total_refs,
                      color: "var(--accent)",
                    },
                    {
                      label: t("texts.paid_refs"),
                      value: stats.paid_refs,
                      color: "var(--success)",
                    },
                    {
                      label: t("texts.total_earned"),
                      value: stats.commission_total
                        ? String(stats.commission_total) + " " + t("texts.currency_rub")
                        : "",
                      color: "var(--warning)",
                    },
                  ]}
                />
              </div>
            </div>
          ) : null}

          <div className="pinned-section fade-in delay-2">
            <h2>{t("texts.actions")}</h2>
            <div className="pinned-content">
              <p className="text-secondary" style={{ marginTop: "16px", fontSize: "14px" }}>
                {t("texts.partner_renew_free_info")}
              </p>
              <div className="form-actions">
                <div className="field-label">
                  <span>{t("texts.partner_period_label", { min: minPeriod, max: maxPeriod })}</span>
                  <span className="number-input-wrapper">
                    <button
                      type="button"
                      className="number-btn"
                      onClick={() =>
                        setPeriodMonths(stepNumber(periodMonths, -1, minPeriod, maxPeriod))
                      }
                    >
                      −
                    </button>
                    <input
                      type="number"
                      aria-label={t("texts.partner_period_label", {
                        min: minPeriod,
                        max: maxPeriod,
                      })}
                      value={periodMonths}
                      onChange={(e) => setPeriodMonths(e.target.value)}
                      min={minPeriod}
                      max={maxPeriod}
                    />
                    <button
                      type="button"
                      className="number-btn"
                      onClick={() =>
                        setPeriodMonths(stepNumber(periodMonths, 1, minPeriod, maxPeriod))
                      }
                    >
                      +
                    </button>
                  </span>
                </div>
                <button className="button" disabled={!telegramLinked} onClick={handleRenew}>
                  {t("buttons.renew_partner")}
                </button>
                {!telegramLinked && (
                  <div className="error-message" style={{ margin: 0 }}>
                    {t("texts.partner_requires_telegram")}{" "}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => router.push("/settings")}
                    >
                      {t("buttons.link_telegram")}
                    </button>
                  </div>
                )}
                {messageBlock}
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
