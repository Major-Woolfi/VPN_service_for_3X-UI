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

export function StatGrid({ cards }: StatGridProps) {
  const { t } = useLanguage();

  return (
    <div className="stat-flex">
      {cards.map((card) => (
        <div key={card.label} className="stat-card">
          <div className="stat-value" style={{ color: card.color }}>
            {card.value}
          </div>
          <div className="stat-label">{card.label}</div>
        </div>
      ))}
      {cards.length === 0 && <div className="stat-card stat-label">{t("texts.no_data")}</div>}
    </div>
  );
}
