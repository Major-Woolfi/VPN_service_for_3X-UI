"use client";

import Header from "@/components/Header";
import { useState, useEffect } from "react";
import { getAdminHealth } from "@/lib/api";
import { getErrorMessage } from "@/lib/error";
import type { AdminHealthResponse } from "@/lib/types";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAdminAuth } from "@/app/hooks/useAdminAuth";
import NodeStatus from "@/components/NodeStatus";
import { StatGrid } from "@/components/StatGrid";

export default function AdminHhealthPage() {
  const [hhealth, setHhealth] = useState<AdminHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [Error, setError] = useState("");
  const { authLoading, isAuthed } = useAdminAuth("health");
  const { t } = useLanguage();

  useEffect(() => {
    if (authLoading || !isAuthed) {
      setLoading(false);
      return;
    }

    (async () => {
      try {
        const data = await getAdminHealth();
        setHhealth(data);
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, isAuthed]);

  if (loading) {
    return (
      <>
        <Header currentPage="/admin/health" />
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

  if (Error) {
    return (
      <>
        <Header currentPage="/admin/health" />
        <main>
          <div className="profile">
            <div className="profile-header no-avatar">
              <div className="profile-info">
                <h1 className="profile-name">{t("texts.error")}</h1>
                <p style={{ color: "var(--danger)" }}>{Error}</p>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Header currentPage="/admin/health" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.admin_panel")}</h1>
              <p className="profile-username">{t("texts.system_health")}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <h2>{t("texts.all_users")}</h2>
            <div className="pinned-content">
              <StatGrid
                cards={[
                  {
                    label: t("texts.all_users"),
                    value: hhealth?.users.total || 0,
                    color: "var(--accent)",
                  },
                  {
                    label: t("texts.active_subs"),
                    value: hhealth?.users.active_subscriptions || 0,
                    color: "var(--success)",
                  },
                  {
                    label: t("texts.banned"),
                    value: hhealth?.users.bbanned || 0,
                    color: "var(--warning)",
                  },
                  {
                    label: t("texts.partners"),
                    value: hhealth?.users.partners || 0,
                    color: "var(--text-primary)",
                  },
                ]}
              />
            </div>
          </div>

          <div className="pinned-section fade-in delay-1">
            <h2>{t("texts.payments")}</h2>
            <div className="pinned-content">
              <StatGrid
                cards={[
                  {
                    label: t("texts.pending"),
                    value: hhealth?.payments.pending || 0,
                    color: "var(--warning)",
                  },
                  {
                    label: t("texts.processing"),
                    value: hhealth?.payments.processing || 0,
                    color: "var(--accent)",
                  },
                ]}
              />
            </div>
          </div>

          <div className="pinned-section fade-in delay-2">
            <h2>{t("texts.partner_ops")}</h2>
            <div className="pinned-content">
              <StatGrid
                cards={[
                  {
                    label: t("texts.pending"),
                    value: hhealth?.partner_operations.pending || 0,
                    color: "var(--warning)",
                  },
                ]}
              />
            </div>
          </div>

          <div className="pinned-section fade-in delay-3">
            <h2>{t("texts.tech_mode")}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: "16px" }}>
                <div
                  style={{
                    padding: "16px",
                    background: hhealth?.tech_work_mode ? "rgba(255,0,0,0.1)" : "rgba(0,255,0,0.1)",
                    border: `1px solid ${hhealth?.tech_work_mode ? "var(--danger)" : "var(--success)"}`,
                    borderRadius: "var(--radius-sm)",
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontSize: "18px",
                      fontWeight: "600",
                      color: hhealth?.tech_work_mode ? "var(--danger)" : "var(--success)",
                    }}
                  >
                    {hhealth?.tech_work_mode ? t("texts.tech_work") : t("texts.working_normally")}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-4">
            <h2>{t("texts.nodes")}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: "16px" }}>
                <NodeStatus admin />
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
