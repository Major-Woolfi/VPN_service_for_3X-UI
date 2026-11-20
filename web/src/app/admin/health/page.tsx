"use client";

import Header from "@/components/Header";
import { useState, useEffect } from "react";
import { getAdminHealth } from "@/lib/api";
import type { AdminHealthResponse } from "@/lib/types";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAdminAuth } from "@/app/hooks/useAdminAuth";
import NodeStatus from "@/components/NodeStatus";

export default function AdminHhealthPage() {
  const [hhealth, setHhealth] = useState<AdminHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [Error, setError] = useState("");
  const { authLoading, isAuthed } = useAdminAuth("health");
  const { t } = useLanguage();

  useEffect(() => {
    if (authLoading || !isAuthed) return;

    (async () => {
      try {
        const data = await getAdminHealth();
        setHhealth(data);
      } catch (err) {
        setError(String(err));
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
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                  gap: "12px",
                  marginTop: "16px",
                }}
              >
                <div
                  style={{
                    padding: "16px",
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
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      maxWidth: "100%",
                    }}
                  >
                    {hhealth?.users.total || 0}
                  </div>
                  <div
                    style={{
                      fontSize: "14px",
                      color: "var(--text-secondary)",
                      marginTop: "8px",
                    }}
                  >
                    {t("texts.all_users")}
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
                    {hhealth?.users.active_subscriptions || 0}
                  </div>
                  <div
                    style={{
                      fontSize: "14px",
                      color: "var(--text-secondary)",
                      marginTop: "8px",
                    }}
                  >
                    {t("texts.active_subs")}
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
                    {hhealth?.users.bbanned || 0}
                  </div>
                  <div
                    style={{
                      fontSize: "14px",
                      color: "var(--text-secondary)",
                      marginTop: "8px",
                    }}
                  >
                    {t("texts.banned")}
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
                      color: "var(--text-primary)",
                    }}
                  >
                    {hhealth?.users.partners || 0}
                  </div>
                  <div
                    style={{
                      fontSize: "14px",
                      color: "var(--text-secondary)",
                      marginTop: "8px",
                    }}
                  >
                    {t("texts.partners")}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-1">
            <h2>{t("texts.payments")}</h2>
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
                    padding: "16px",
                    background: "var(--bg-tertiary)",
                    borderRadius: "var(--radius-md)",
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontSize: "24px",
                      fontWeight: "700",
                      color: "var(--warning)",
                    }}
                  >
                    {hhealth?.payments.pending || 0}
                  </div>
                  <div
                    style={{ fontSize: "14px", color: "var(--text-secondary)" }}
                  >
                    {t("texts.pending")}
                  </div>
                </div>
                <div
                  style={{
                    padding: "16px",
                    background: "var(--bg-tertiary)",
                    borderRadius: "var(--radius-md)",
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontSize: "24px",
                      fontWeight: "700",
                      color: "var(--accent)",
                    }}
                  >
                    {hhealth?.payments.processing || 0}
                  </div>
                  <div
                    style={{ fontSize: "14px", color: "var(--text-secondary)" }}
                  >
                    {t("texts.processing")}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-2">
            <h2>{t("texts.partner_ops")}</h2>
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
                    padding: "16px",
                    background: "var(--bg-tertiary)",
                    borderRadius: "var(--radius-md)",
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontSize: "24px",
                      fontWeight: "700",
                      color: "var(--warning)",
                    }}
                  >
                    {hhealth?.partner_operations.pending || 0}
                  </div>
                  <div
                    style={{ fontSize: "14px", color: "var(--text-secondary)" }}
                  >
                    {t("texts.pending")}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-3">
            <h2>{t("texts.tech_mode")}</h2>
            <div className="pinned-content">
              <div style={{ marginTop: "16px" }}>
                <div
                  style={{
                    padding: "16px",
                    background: hhealth?.tech_work_mode
                      ? "rgba(255,0,0,0.1)"
                      : "rgba(0,255,0,0.1)",
                    border: `1px solid ${hhealth?.tech_work_mode ? "var(--danger)" : "var(--success)"}`,
                    borderRadius: "var(--radius-sm)",
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontSize: "18px",
                      fontWeight: "600",
                      color: hhealth?.tech_work_mode
                        ? "var(--danger)"
                        : "var(--success)",
                    }}
                  >
                    {hhealth?.tech_work_mode
                      ? t("texts.tech_work")
                      : t("texts.working_normally")}
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


















