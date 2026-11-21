"use client";

import Header from "@/components/Header";
import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { getUsers } from "@/lib/api";
import { getErrorMessage } from "@/lib/error";
import type { UserListResponse } from "@/lib/types";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAdminAuth } from "@/app/hooks/useAdminAuth";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserListResponse["users"]>([]);
  const [coOwners, setCoOwners] = useState<UserListResponse["users"]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [Error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const { authLoading, authUser, isAuthed } = useAdminAuth("users");
  const router = useRouter();
  const { t } = useLanguage();

  const limit = 50;
  const pageRef = useRef(page);
  pageRef.current = page;

  const loadUsers = useCallback(async () => {
    if (!isAuthed) return;
    setLoading(true);
    setError("");
    try {
      const data = await getUsers(pageRef.current, limit, debouncedSearch);
      setUsers(data.users);
      setTotal(data.total);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [isAuthed, limit, debouncedSearch]);

  useEffect(() => {
    if (authLoading || !isAuthed) return;
    void loadUsers();
  }, [authLoading, router, loadUsers, authUser, isAuthed, page]);

  useEffect(() => {
    const id = setTimeout(() => {
      setPage(1);
      setDebouncedSearch(searchTerm.trim());
    }, 300);
    return () => clearTimeout(id);
  }, [searchTerm]);

  useEffect(() => {
    if (authLoading || !isAuthed) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getUsers(1, 200, "", true);
        if (!cancelled) setCoOwners(data.users);
      } catch {
        if (!cancelled) setCoOwners([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthed]);

  const totalPages = Math.ceil(total / limit);

  return (
    <>
      <Header currentPage="/admin/users" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.users_list")}</h1>
              <p className="profile-username">
                {t("texts.users_count")} ({total})
              </p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div style={{ marginTop: "16px", marginBottom: "16px" }}>
                <input
                  type="text"
                  aria-label={t("texts.search_placeholder")}
                  placeholder={t("texts.search_placeholder")}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="faq-search-input"
                />
              </div>
              {loading && <p className="text-center text-secondary">{t("texts.loading")}</p>}
              {Error && (
                <div style={{ marginBottom: "16px" }}>
                  <p style={{ color: "var(--danger)", margin: 0 }}>{Error}</p>
                </div>
              )}
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("texts.user_id")}</th>
                      <th>{t("texts.telegram_username_label")}</th>
                      <th>{t("texts.telegram_id_label")}</th>
                      <th>{t("texts.subscription_status")}</th>
                      <th>{t("buttons.partner")}</th>
                      <th>{t("texts.trust_score")}</th>
                      <th>{t("texts.abuse")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.user_id}>
                        <td className="data-num" data-label={t("texts.user_id")}>
                          {u.user_id}
                        </td>
                        <td data-label={t("texts.telegram_username_label")}>{u.username || "-"}</td>
                        <td className="data-num" data-label={t("texts.telegram_id_label")}>
                          {u.telegram_id || "-"}
                        </td>
                        <td data-label={t("texts.subscription_status")}>
                          <span
                            style={{
                              padding: "4px 8px",
                              background: u.has_subscription
                                ? "var(--success-solid)"
                                : "var(--bg-tertiary)",
                              borderRadius: "var(--radius-sm)",
                              color: u.has_subscription ? "#fff" : "var(--text-secondary)",
                              fontSize: "12px",
                            }}
                          >
                            {u.has_subscription ? t("texts.status_active") : t("texts.no")}
                          </span>
                        </td>
                        <td data-label={t("buttons.partner")}>
                          <span
                            style={{
                              padding: "4px 8px",
                              background: u.is_mate ? "var(--accent-solid)" : "var(--bg-tertiary)",
                              borderRadius: "var(--radius-sm)",
                              color: u.is_mate ? "#fff" : "var(--text-secondary)",
                              fontSize: "12px",
                            }}
                          >
                            {u.is_mate ? t("texts.yes") : t("texts.no")}
                          </span>
                        </td>
                        <td className="data-num" data-label={t("texts.trust_score")}>
                          {u.trust_score}
                        </td>
                        <td data-label={t("texts.abuse")}>
                          {u.abuse_status ? (
                            <span
                              style={{
                                padding: "4px 8px",
                                background: "var(--danger)",
                                borderRadius: "var(--radius-sm)",
                                color: "#fff",
                                fontSize: "12px",
                              }}
                            >
                              {u.abuse_status}
                            </span>
                          ) : (
                            "-"
                          )}
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr>
                        <td
                          colSpan={7}
                          style={{
                            textAlign: "center",
                            color: "var(--text-secondary)",
                            padding: "24px",
                          }}
                        >
                          {searchTerm ? t("texts.search_no_results") : t("texts.no_data")}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="pinned-section fade-in delay-1">
            <h2>{t("texts.co_owner_title")}</h2>
            <div className="pinned-content">
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("texts.user_id")}</th>
                      <th>{t("texts.telegram_id_label")}</th>
                      <th>{t("texts.co_owner_date")}</th>
                      <th>{t("texts.telegram_username_label")}</th>
                      <th>{t("texts.co_owner_subscription")}</th>
                      <th>{t("texts.co_owner_subscription_id")}</th>
                      <th>{t("texts.co_owner_vpn_url")}</th>
                      <th>{t("texts.co_owner_expiry")}</th>
                      <th>{t("texts.co_owner_parent")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coOwners.map((u) => (
                      <tr key={u.user_id}>
                        <td className="data-num" data-label={t("texts.user_id")}>
                          {u.user_id}
                        </td>
                        <td className="data-num" data-label={t("texts.telegram_id_label")}>
                          {u.telegram_id || "-"}
                        </td>
                        <td data-label={t("texts.co_owner_date")}>{u.join_date || "-"}</td>
                        <td data-label={t("texts.telegram_username_label")}>{u.username || "-"}</td>
                        <td data-label={t("texts.co_owner_subscription")}>
                          {u.has_subscription ? t("texts.yes") : t("texts.no")}
                        </td>
                        <td data-label={t("texts.co_owner_subscription_id")}>
                          {u.subscription_id || "-"}
                        </td>
                        <td data-label={t("texts.co_owner_vpn_url")}>{u.vpn_url || "-"}</td>
                        <td data-label={t("texts.co_owner_expiry")}>
                          {u.expiry_sub_datatime || "-"}
                        </td>
                        <td className="data-num" data-label={t("texts.co_owner_parent")}>
                          {u.ref_by || "-"}
                        </td>
                      </tr>
                    ))}
                    {coOwners.length === 0 && (
                      <tr>
                        <td
                          colSpan={9}
                          style={{
                            textAlign: "center",
                            color: "var(--text-secondary)",
                            padding: "24px",
                          }}
                        >
                          {t("texts.no_data")}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {totalPages > 1 && (
            <div
              className="dashboard-actions"
              style={{
                justifyContent: "center",
                marginTop: "24px",
              }}
            >
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1 || loading}
                className="button"
                style={{ opacity: page === 1 ? 0.5 : 1 }}
              >
                {t("buttons.back")}
              </button>
              <span style={{ padding: "12px", fontSize: "14px" }}>
                {t("texts.page_of", { page, total: totalPages })}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages || loading}
                className="button"
                style={{ opacity: page === totalPages ? 0.5 : 1 }}
              >
                {t("buttons.forward")}
              </button>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
