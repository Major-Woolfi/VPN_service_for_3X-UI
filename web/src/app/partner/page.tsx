"use client";

import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import { StatGrid } from "@/components/StatGrid";
import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { useFeatures } from "@/contexts/FeaturesContext";
import {
  getPartnerProfile,
  getPartnerStats,
  getPartnerPublicInfo,
  partnerApply,
  partnerRenew,
} from "@/lib/api";
import type {
  PartnerProfileResponse,
  PartnerStatsResponse,
  PartnerPublicInfoResponse,
} from "@/lib/types";

export default function PartnerPage() {
  const { user, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const { features } = useFeatures();
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
    if (!user?.is_partner) return;
    let cancelled = false;
    (async () => {
      try {
        const [p, s, pi] = await Promise.all([
          getPartnerProfile(),
          getPartnerStats(),
          getPartnerPublicInfo(),
        ]);
        if (!cancelled) {
          setProfile(p);
          setStats(s);
          setPublicInfo(pi);
        }
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [user?.is_partner]);

  const isPartner = Boolean(user?.is_partner);
  const isPending = Boolean(user?.pending_partner_application);
  const telegramLinked = Boolean(user?.telegram_id);
  const minPeriod = publicInfo?.min_period_months || 1;
  const maxPeriod = publicInfo?.max_period_months || 12;
  const minFollowers = publicInfo?.min_followers || 0;
  const bmin = publicInfo?.bonus_days_min || 0;
  const bmax = publicInfo?.bonus_days_max || 0;

  const handleApply = async () => {
    setSubmitting(true);
    setMessage("");
    try {
      await partnerApply({
        followers: parseInt(followers, 10) || 0,
        social_links: socials,
        nickname,
        period_months: parseInt(periodMonths, 10) || 0,
        bonus_type: bonusType,
        bonus_value: parseInt(bonusValue, 10) || 0,
      });
      setMessage(t("texts.partner_applied"));
      setIsError(false);
    } catch (err) {
      setMessage(String(err));
      setIsError(true);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRenew = async () => {
    try {
      await partnerRenew({ months: parseInt(periodMonths, 10) || 1 });
      setMessage(t("texts.partner_renewed"));
      setIsError(false);
    } catch (err) {
      setMessage(String(err));
      setIsError(true);
    }
  };

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
            <div style={{ marginTop: "24px", textAlign: "center" }}>
              <p style={{ marginBottom: "16px", color: "var(--text-secondary)" }}>{t("texts.login_required_partner")}</p>
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                <button onClick={() => router.push("/login?next=/partner")} className="button" style={{ flex: 1 }}>
                  {t("buttons.login")}
                </button>
                <button onClick={() => router.push("/register?next=/partner")} className="button" style={{ flex: 1, background: "var(--bg-tertiary)", color: "var(--text-primary)" }}>
                  {t("buttons.register")}
                </button>
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
            <div style={{ marginTop: "24px" }}>
              {isPending ? (
                <p style={{ color: "var(--text-secondary)" }}>{t("texts.pending")}</p>
              ) : (
                <form onSubmit={(e) => { e.preventDefault(); handleApply(); }} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <button type="button" onClick={() => setFollowers(String(Math.max(minFollowers, (parseInt(followers, 10) || 0) - 1)))}>−</button>
                    <input type="number" value={followers} onChange={(e) => setFollowers(e.target.value)} placeholder={t("texts.partner_followers")} className="form-input" required min={String(minFollowers)} />
                    <button type="button" onClick={() => setFollowers(String((parseInt(followers, 10) || 0) + 1))}>+</button>
                  </div>
                  <input type="text" value={socials} onChange={(e) => setSocials(e.target.value)} placeholder={t("texts.partner_apply_socials_placeholder")} className="form-input" required />
                  <input type="text" value={nickname} onChange={(e) => setNickname(e.target.value)} placeholder={t("texts.partner_nickname")} className="form-input" required />
                  <input type="number" value={periodMonths} onChange={(e) => setPeriodMonths(e.target.value)} placeholder={t("texts.partner_period_label", { min: minPeriod, max: maxPeriod })} className="form-input" required min={String(minPeriod)} max={String(maxPeriod)} />
                  <select value={bonusType} onChange={(e) => { setBonusType(e.target.value); setBonusValue(""); }} className="form-input">
                    <option value="days">{t("texts.partner_bonus_days", { min: publicInfo?.bonus_days_min || 0, max: publicInfo?.bonus_days_max || 0 })}</option>
                    <option value="trust">{t("texts.partner_trust_points", { min: publicInfo?.trust_points_min || 0, max: publicInfo?.trust_points_max || 0 })}</option>
                  </select>
                  <input type="number" value={bonusValue} onChange={(e) => setBonusValue(e.target.value)} placeholder={t("texts.partner_trust_placeholder", { min: bmin, max: bmax })} className="form-input" />
                  {message ? (
                    <div style={{ padding: "12px", background: "var(--bg-tertiary)", borderRadius: "var(--radius-sm)", color: isError ? "var(--danger)" : "var(--success)", fontSize: "14px" }}>
                      {message}
                    </div>
                  ) : null}
                  <button type="submit" className="button" style={{ width: "100%" }} disabled={submitting || !telegramLinked}>
                    {submitting ? t("texts.waiting") : t("texts.partner_apply_submit")}
                  </button>
                </form>
              )}
              <p style={{ marginTop: "16px", color: "var(--text-secondary)" }}>{t("texts.partner_apply_text")}</p>
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
            <div style={{ marginTop: "16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.web_login")}</span>
                <span>{profile.ref_link_code}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border-color)" }}>
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.status")}</span>
                <span style={{ color: profile.status === "active" ? "var(--success)" : "var(--warning)" }}>{profile.status === "active" ? t("texts.status_active") : t("texts.pending")}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-secondary)" }}>{t("texts.referral_link")}</span>
                {profile.ref_link ? (
                  <a href={profile.ref_link} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", wordBreak: "break-all" }}>{profile.ref_link}</a>
                ) : (
                  <span style={{ color: "var(--text-secondary)" }}>{profile.ref_link_code || t("texts.not_specified")}</span>
                )}
              </div>
            </div>
          ) : null}

          {stats ? (
            <StatGrid cards={[
              { label: t("texts.total_refs"), value: stats.total_refs, color: "var(--accent)" },
              { label: t("texts.paid_refs"), value: stats.paid_refs, color: "var(--success)" },
              { label: t("texts.total_earned"), value: stats.commission_total ? String(stats.commission_total) + " " + t("texts.currency_rub") : "", color: "var(--warning)" },
            ]} />
          ) : null}

          <div style={{ marginTop: "24px" }}>
            <h2 style={{ marginBottom: "16px", color: "var(--text-secondary)" }}>{t("texts.actions")}</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <button className="button" style={{ width: "100%" }} onClick={() => {}}>{t("buttons.withdraw")}</button>
              <button className="button" style={{ width: "100%" }} disabled={!telegramLinked} onClick={handleRenew}>{t("buttons.renew_partner")}</button>
              {message ? (
                <div style={{ padding: "12px", background: "var(--bg-tertiary)", borderRadius: "var(--radius-sm)", color: isError ? "var(--danger)" : "var(--success)", fontSize: "14px" }}>
                  {message}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
