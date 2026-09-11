'use client';

import { useState, useMemo, useCallback } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';

export default function FaqList() {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<number | null>(null);

  const allFaq = useMemo(() => {
    const items: { id: number; question: string; answer: string; category: string }[] = [];
    for (let i = 1; i <= 12; i++) {
      const question = t(`texts.qa_question_${i}`);
      const answer = t(`texts.qa_answer_${i}`);
      const category = t(`texts.qa_category_${i}`);
      if (question && answer && question !== `texts.qa_question_${i}` && answer !== `texts.qa_answer_${i}`) {
        items.push({ id: i, question, answer, category });
      }
    }
    return items;
  }, [t]);

  const allCategories = useMemo(() => {
    const cats = new Set<string>();
    for (const item of allFaq) {
      if (item.category) cats.add(item.category);
    }
    return Array.from(cats);
  }, [allFaq]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return allFaq;
    return allFaq.filter(
      (item) => item.question.toLowerCase().includes(q) || item.answer.toLowerCase().includes(q),
    );
  }, [query, allFaq]);

  const grouped = useMemo(() => {
    const map = new Map<string, { id: number; question: string; answer: string; category: string }[]>();
    for (const item of filtered) {
      const arr = map.get(item.category) || [];
      arr.push(item);
      map.set(item.category, arr);
    }
    return map;
  }, [filtered]);

  const toggle = useCallback((id: number) => {
    setOpenId((prev) => (prev === id ? null : id));
  }, []);

  return (
    <div className="faq-section">
      <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpenId(null);
          }}
          placeholder={t('texts.qa_search_placeholder')}
          className="faq-search-input"
          aria-label={t('texts.qa_search_placeholder')}
        />
        <div className="faq-count">
          {t('texts.qa_show_count', { count: filtered.length, total: allFaq.length })}
        </div>
        {filtered.length === 0 && (
          <div className="faq-no-results">
            <p>{t('texts.qa_no_results')}</p>
          </div>
        )}
      </div>

      <div className="faq-list">
        {allCategories.map((category) => {
          const items = grouped.get(category);
          if (!items || items.length === 0) return null;
          return (
            <div key={category}>
              <h3>{category}</h3>
              {items.map((item) => {
                const isOpen = openId === item.id;
                return (
                  <section key={item.id} className={`faq-item${isOpen ? ' open' : ''}`}>
                    <button
                      type="button"
                      className="faq-question"
                      aria-expanded={isOpen}
                      aria-controls={`faq-answer-${item.id}`}
                      onClick={() => toggle(item.id)}
                    >
                      <span>
                        {item.id}. {item.question}
                      </span>
                    </button>
                      <div className="faq-answer-wrapper">
                        <div id={`faq-answer-${item.id}`} className="faq-answer" role="region">
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

