"use client";

import type { Tariff } from "@/lib/types";
import { formatTariffDuration, formatTariffTraffic } from "@/lib/i18n";
import { useFeatures } from "@/contexts/FeaturesContext";
import { useLanguage } from "@/contexts/LanguageContext";

export default function TariffGrid({
  tariffs,
  onSelect,
  disabled = false,
  tariffMode,
}: {
  tariffs: Tariff[];
  onSelect?: (tariff: Tariff) => void;
  disabled?: boolean;
  tariffMode?: "old" | "new";
}) {
  const { t, lang } = useLanguage();
  const { features } = useFeatures();
  const mode = tariffMode ?? features?.features?.tariff_mode;
  const isNewMode = mode === "new";
  const locationLabels = Array.from(new Set(tariffs.flatMap((tariff) => tariff.locations ?? [])));

  return (
    <>
      <div className="tariff-grid">
        {tariffs.map((tariff) => (
          <button
            key={tariff.id}
            type="button"
            className="card tariff-card"
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              padding: "20px",
              width: "100%",
              border: "none",
              font: "inherit",
              textAlign: "left",
              cursor: onSelect ? "pointer" : "default",
            }}
            disabled={!onSelect || disabled}
            onClick={() => onSelect?.(tariff)}
          >
            {isNewMode ? (
              <div style={{ textAlign: "center" }}>
                <div style={{ fontWeight: 600, fontSize: "16px" }}>
                  {tariff.name} - {tariff.price_rub} ₽
                </div>
                <div className="text-secondary" style={{ fontSize: "13px", marginTop: "4px" }}>
                  {formatTariffDuration(tariff.duration_days, lang)}
                </div>
                <div className="text-secondary" style={{ fontSize: "13px", marginTop: "4px" }}>
                  {formatTariffTraffic(tariff.traffic_gb, true, lang)} · {tariff.ip_limit}{" "}
                  {t("texts.ip_label")}
                </div>
              </div>
            ) : (
              <>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontWeight: 600, fontSize: "16px" }}>{tariff.name}</div>
                  <div className="text-secondary" style={{ fontSize: "13px", marginTop: "4px" }}>
                    {formatTariffTraffic(tariff.traffic_gb, false, lang)} · {tariff.ip_limit}{" "}
                    {t("texts.ip_label")} · {formatTariffDuration(tariff.duration_days, lang)}
                  </div>
                  {(tariff.locations ?? []).length > 0 && (
                    <div className="text-secondary" style={{ fontSize: "13px", marginTop: "4px" }}>
                      {(tariff.locations ?? []).join(", ")}
                    </div>
                  )}
                </div>
                <div
                  style={{
                    fontWeight: 700,
                    color: "var(--accent)",
                    fontSize: "18px",
                    marginTop: "12px",
                  }}
                >
                  {tariff.price_rub} ₽
                </div>
              </>
            )}
          </button>
        ))}
      </div>
      {isNewMode && locationLabels.length > 0 && (
        <div className="info-block" role="note">
          {t("texts.available_locations", { locations: locationLabels.join(", ") })}
        </div>
      )}
    </>
  );
}
