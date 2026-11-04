"use client";

import { useState, useMemo, useCallback } from "react";
import { useLanguage } from "@/contexts/LanguageContext";

type FaqItem = {
  id: string;
  question: string;
  answer: string;
  category: string;
  categoryKey: string;
};

type FaqCategory = {
  key: string;
  title: string;
  items: FaqItem[];
};

export default function FaqList() {
  const { t, tObject, lang } = useLanguage();
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const allCategories = useMemo((): FaqCategory[] => {
    const qaData = tObject("qa.category", lang) as Record<string, { title?: string; content?: Record<string, { question: string; answer: string }> }> | undefined;
    if (!qaData) return [];

    const categories: FaqCategory[] = [];

    for (const [categoryKey, categoryData] of Object.entries(qaData)) {
      if (!categoryData || typeof categoryData !== "object") continue;

      const catData = categoryData as { title?: string; content?: Record<string, { question: string; answer: string }> };
      if (!catData.content) continue;

      const items: FaqItem[] = [];
      for (const [qId, qData] of Object.entries(catData.content)) {
        if (qData.question && qData.answer) {
          items.push({
            id: `${categoryKey}-${qId}`,
            question: qData.question,
            answer: qData.answer,
            category: catData.title || categoryKey,
            categoryKey,
          });
        }
      }

      if (items.length > 0) {
        items.sort((a, b) => Number(a.id.split("-")[1]) - Number(b.id.split("-")[1]));
        categories.push({
          key: categoryKey,
          title: catData.title || categoryKey,
          items,
        });
      }
    }

    return categories;
  }, [tObject, lang]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return allCategories;

    return allCategories
      .map((cat) => ({
        ...cat,
        items: cat.items.filter(
          (item) =>
            item.question.toLowerCase().includes(q) ||
            item.answer.toLowerCase().includes(q),
        ),
      }))
      .filter((cat) => cat.items.length > 0);
  }, [query, allCategories]);

  const totalQuestions = useMemo(
    () => allCategories.reduce((sum, cat) => sum + cat.items.length, 0),
    [allCategories],
  );
  const filteredCount = useMemo(
    () => filtered.reduce((sum, cat) => sum + cat.items.length, 0),
    [filtered],
  );

  const toggle = useCallback((id: string) => {
    setOpenId((prev) => (prev === id ? null : id));
  }, []);

  return (
    <div className="faq-section">
      <div
        style={{
          marginTop: "16px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpenId(null);
          }}
          placeholder={t("texts.qa_search_placeholder")}
          className="faq-search-input"
          aria-label={t("texts.qa_search_placeholder")}
        />
        <div className="faq-count">
          {t("texts.qa_show_count", {
            count: filteredCount,
            total: totalQuestions,
          })}
        </div>
        {filteredCount === 0 && (
          <div className="faq-no-results">
            <p>{t("texts.qa_no_results")}</p>
          </div>
        )}
      </div>

      <div className="faq-list">
        {filtered.map((category) => (
          <div key={category.key}>
            <h3>{category.title}</h3>
            {category.items.map((item, index) => {
              const isOpen = openId === item.id;
              return (
                <section
                  key={item.id}
                  className={`faq-item${isOpen ? " open" : ""}`}
                >
                  <button
                    type="button"
                    className="faq-question"
                    aria-expanded={isOpen}
                    aria-controls={`faq-answer-${item.id}`}
                    onClick={() => toggle(item.id)}
                  >
                    <span>
                      {index + 1}. {item.question}
                    </span>
                  </button>
                  <div className="faq-answer-wrapper">
                    <div
                      id={`faq-answer-${item.id}`}
                      className="faq-answer"
                      role="region"
                    >
                      <div className="faq-answer-inner">
                        <p>{item.answer}</p>
                      </div>
                    </div>
                  </div>
                </section>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}