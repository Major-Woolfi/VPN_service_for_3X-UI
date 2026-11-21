import Header from "@/components/Header";
import { tServer, resolvelanguage, getServerLegalDocument } from "@/lib/i18n-server";
import { SafeHTML } from "@/components/SafeHTML";
import { cookies, headers } from "next/headers";

type LegalDocType = "offer" | "tos" | "privacy";

interface LegalDocumentPageProps {
  docType: LegalDocType;
  page: string;
}

export default async function LegalDocumentPage({ docType, page }: LegalDocumentPageProps) {
  const cookieStore = await cookies();
  const headerStore = await headers();
  const lang = resolvelanguage(
    cookieStore.get("vpn_language")?.value,
    headerStore.get("accept-language") || undefined,
  );
  const t = (key: string, params?: Record<string, string | number>) => tServer(lang, key, params);
  const copy = getServerLegalDocument(lang, docType);

  return (
    <>
      <Header currentPage={`/${page}`} />
      <main>
        <div className="profile">
          <div className="profile-header no-avatar">
            <div className="profile-info">
              <h1 className="profile-name">{copy.title}</h1>
              <p className="profile-username">{copy.subtitle}</p>
            </div>
          </div>

          <div className="pinned-section fade-in">
            <div className="pinned-content">
              <div style={{ marginTop: "16px", lineHeight: "1.6" }}>
                <p
                  style={{
                    color: "var(--text-secondary)",
                    marginBottom: "16px",
                  }}
                >
                  <strong>
                    {t("texts.effective_date", {
                      date: copy.effectiveDate,
                    })}
                  </strong>
                </p>
                {copy.sections.map((section, idx) => (
                  <div key={idx}>
                    <h2 style={{ marginTop: idx === 0 ? "0" : "24px" }}>{section.title}</h2>
                    <div style={{ color: "var(--text-secondary)" }}>
                      <SafeHTML html={section.content} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
