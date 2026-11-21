"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { getCoOwnerUsers } from "@/lib/api";
import { getErrorMessage } from "@/lib/error";
import type { CoOwnerUser, CoOwnerUsersResponse } from "@/lib/types";

type CoOwnerField = keyof CoOwnerUser;

const USER_FIELDS: readonly { key: CoOwnerField; labelKey: string }[] = [
  { key: "user_id", labelKey: "texts.user_id" },
  { key: "telegram_id", labelKey: "texts.telegram_id_label" },
  { key: "join_date", labelKey: "texts.co_owner_join_date" },
  { key: "username", labelKey: "texts.telegram_username_label" },
  { key: "has_subscription", labelKey: "texts.co_owner_has_subscription" },
  { key: "subscription_id", labelKey: "texts.co_owner_subscription_id" },
  { key: "vpn_url", labelKey: "texts.co_owner_vpn_url" },
  { key: "expiry_sub_datatime", labelKey: "texts.co_owner_expiry" },
  { key: "ref_by", labelKey: "texts.co_owner_ref_by" },
];

const ALL_FIELDS = new Set<CoOwnerField>(USER_FIELDS.map((field) => field.key));

function escapeCsv(value: CoOwnerUser[CoOwnerField]): string {
  const text = typeof value === "boolean" ? (value ? "true" : "false") : String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export default function CoOwnersPage() {
  const { user, loading: authLoading } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();

  const [users, setUsers] = useState<CoOwnerUsersResponse | null>(null);
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedFields, setSelectedFields] = useState<Set<CoOwnerField>>(
    () => new Set(ALL_FIELDS),
  );

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(searchTerm.trim()), 300);
    return () => clearTimeout(id);
  }, [searchTerm]);

  useEffect(() => {
    if (authLoading) return;
    if (!user?.user_id) {
      router.replace("/login?next=/co-owners");
      return;
    }
    if (!user.is_coowner) {
      router.replace("/profile");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        if (!cancelled) {
          setMessage("");
          setIsError(false);
        }
        const result = await getCoOwnerUsers(debouncedSearch);
        if (!cancelled) setUsers(result);
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
  }, [authLoading, debouncedSearch, router, user?.is_coowner, user?.user_id]);

  const toggleField = (field: CoOwnerField) => {
    setSelectedFields((current) => {
      const next = new Set(current);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });
  };

  const handleDownload = () => {
    const fields = USER_FIELDS.filter((field) => selectedFields.has(field.key));
    if (!fields.length || !users) return;
    const rows = [
      fields.map((field) => escapeCsv(field.key)).join(","),
      ...users.users.map((item) => fields.map((field) => escapeCsv(item[field.key])).join(",")),
    ];
    const blob = new Blob([`\uFEFF${rows.join("\r\n")}`], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "co-owner-users.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <Header currentPage="/co-owners" />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{t("texts.co_owner_title")}</h1>
              <p className="profile-username">{t("texts.co_owner_subtitle")}</p>
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
            <h2>{t("texts.co_owner_users")}</h2>
            <div className="pinned-content">
              <div className="export-panel">
                <div className="export-panel-header">
                  <strong>{t("texts.csv_fields")}</strong>
                  <div className="export-actions">
                    <button
                      type="button"
                      className="button"
                      onClick={() => setSelectedFields(new Set(ALL_FIELDS))}
                    >
                      {t("texts.csv_select_all")}
                    </button>
                    <button
                      type="button"
                      className="button"
                      onClick={() => setSelectedFields(new Set<CoOwnerField>())}
                    >
                      {t("texts.csv_clear_all")}
                    </button>
                  </div>
                </div>
                <div className="export-field-grid">
                  {USER_FIELDS.map((field) => (
                    <label key={field.key} className="export-field">
                      <input
                        type="checkbox"
                        checked={selectedFields.has(field.key)}
                        onChange={() => toggleField(field.key)}
                      />
                      <span>{t(field.labelKey)}</span>
                    </label>
                  ))}
                </div>
                <p className="text-secondary" style={{ margin: 0 }}>
                  {t("texts.csv_export_hint")}
                </p>
                <div className="export-actions">
                  <button
                    type="button"
                    className="button"
                    onClick={handleDownload}
                    disabled={selectedFields.size === 0 || !users}
                  >
                    {t("buttons.download_csv")}
                  </button>
                </div>
              </div>

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

              <div className="data-table-wrap" style={{ marginTop: "16px" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      {USER_FIELDS.map((field) => (
                        <th key={field.key}>{t(field.labelKey)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(users?.users ?? []).map((item) => (
                      <tr key={item.user_id}>
                        <td className="data-num" data-label={t("texts.user_id")}>
                          {item.user_id}
                        </td>
                        <td className="data-num" data-label={t("texts.telegram_id_label")}>
                          {item.telegram_id || "-"}
                        </td>
                        <td data-label={t("texts.co_owner_join_date")}>{item.join_date || "-"}</td>
                        <td data-label={t("texts.telegram_username_label")}>
                          {item.username || "-"}
                        </td>
                        <td data-label={t("texts.co_owner_has_subscription")}>
                          {item.has_subscription ? t("texts.status_active") : t("texts.no")}
                        </td>
                        <td data-label={t("texts.co_owner_subscription_id")}>
                          {item.subscription_id || "-"}
                        </td>
                        <td data-label={t("texts.co_owner_vpn_url")}>{item.vpn_url || "-"}</td>
                        <td data-label={t("texts.co_owner_expiry")}>
                          {item.expiry_sub_datatime || "-"}
                        </td>
                        <td className="data-num" data-label={t("texts.co_owner_ref_by")}>
                          {item.ref_by || "-"}
                        </td>
                      </tr>
                    ))}
                    {users !== null && users.users.length === 0 && (
                      <tr>
                        <td
                          colSpan={USER_FIELDS.length}
                          style={{
                            textAlign: "center",
                            color: "var(--text-secondary)",
                            padding: "24px",
                          }}
                        >
                          {debouncedSearch
                            ? t("texts.search_no_results")
                            : t("texts.co_owner_empty")}
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
