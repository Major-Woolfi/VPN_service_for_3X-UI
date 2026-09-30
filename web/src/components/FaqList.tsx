"use client";

import { useState, useMemo, useCallback } from "react";
import { useLanguage } from "@/contexts/LanguageContext";

const QUESTION_CATEGORY = [
  5, 7, 8, 9, 7, 7, 2, 2, 2, 1, 1, 1, 3, 3, 3, 3, 4, 4, 4, 4, 6, 6, 6, 6, 6, 6,
  10, 10, 10, 11, 14, 14, 12, 13, 15,
];

type FaqItem = {
  id: number;
  question: string;
  answer: string;
  category: string;
  categoryIndex: number;
};

export default function FaqList() {
  const { t } = useLanguage();
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);

  const allFaq = useMemo(() => {
    const items: FaqItem[] = [];
    for (let i = 0; i < QUESTION_CATEGORY.length; i++) {
      const id = i + 1;
      const question = t(`texts.qa_question_${id}`);
      const answer = t(`texts.qa_answer_${id}`);
      const categoryIndex = QUESTION_CATEGORY[i];
      const category = t(`texts.qa_category_${categoryIndex}`);
      if (
        question &&
        answer &&
        question !== `texts.qa_question_${id}` &&
        answer !== `texts.qa_answer_${id}`
      ) {
        items.push({ id, question, answer, category, categoryIndex });
      }
    }
    return items;
  }, [t]);

  const allCategories = useMemo(() => {
    const cats = new Map<number, string>();
    for (const item of allFaq) {
      cats.set(item.categoryIndex, item.category);
    }
    return Array.from(cats.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([index, category]) => ({ index, category }));
  }, [allFaq]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return allFaq;
    return allFaq.filter(
      (item) =>
        item.question.toLowerCase().includes(q) ||
        item.answer.toLowerCase().includes(q),
    );
  }, [query, allFaq]);

  const grouped = useMemo(() => {
    const map = new Map<number, FaqItem[]>();
    for (const item of filtered) {
      const arr = map.get(item.categoryIndex) || [];
      arr.push(item);
      map.set(item.categoryIndex, arr);
    }
    for (const arr of map.values()) {
      arr.sort((a, b) => a.id - b.id);
    }
    return map;
  }, [filtered]);

  const toggle = useCallback((id: number) => {
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
            count: filtered.length,
            total: allFaq.length,
          })}
        </div>
        {filtered.length === 0 && (
          <div className="faq-no-results">
            <p>{t("texts.qa_no_results")}</p>
          </div>
        )}
      </div>

      <div className="faq-list">
        {allCategories.map(({ index, category }) => {
          const items = grouped.get(index);
          if (!items || items.length === 0) return null;
          return (
            <div key={category}>
              <h3>{category}</h3>
              {items.map((item, index) => {
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
          );
        })}
      </div>
    </div>
  );
}
