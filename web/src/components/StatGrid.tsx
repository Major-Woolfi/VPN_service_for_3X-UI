"use client";

import { useLanguage } from "@/contexts/LanguageContext";

interface StatCard {
  label: string;
  value: string | number;
  color?: string;
}

interface StatGridProps {
  cards: StatCard[];
}

/**
 * Сетка карточек статистики.
 * Адаптив задаётся классом .grid-auto-fit: одна колонка на телефоне,
 * две на планшете, auto-fit на широких экранах.
 */
export function StatGrid({ cards }: StatGridProps) {
  const { t } = useLanguage();

  return (
    <div className="grid-auto-fit" style={{ marginTop: "16px" }}>
      {cards.map((card) => (
        <div
          key={card.label}
          style={{
            padding: "20px",
            background: "var(--bg-tertiary)",
            borderRadius: "var(--radius-md)",
            textAlign: "center",
          }}
        >
          <div
            className="stat-value"
            style={{ fontSize: "28px", fontWeight: "700", color: card.color }}
          >
            {card.value}
          </div>
          <div
            style={{
              fontSize: "14px",
              color: "var(--text-secondary)",
              marginTop: "8px",
            }}
          >
            {card.label}
          </div>
        </div>
      ))}
      {cards.length === 0 && (
        <div
          className="stat-value"
          style={{
            padding: "20px",
            color: "var(--text-secondary)",
            fontSize: "14px",
          }}
        >
          {t("texts.no_data")}
        </div>
      )}
    </div>
  );
}
