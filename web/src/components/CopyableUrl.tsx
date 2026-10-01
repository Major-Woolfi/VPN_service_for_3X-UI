"use client";

import { useLanguage } from "@/contexts/LanguageContext";

interface CopyableUrlProps {
  url: string;
  onCopy: () => void;
  copied: boolean;
}

/**
 * Блок со ссылкой на подписку и кнопкой копирования.
 * Ссылка длинная, поэтому переносится по словам вместо горизонтальной
 * прокрутки на мобильных экранах.
 */
export function CopyableUrl({ url, onCopy, copied }: CopyableUrlProps) {
  const { t } = useLanguage();

  return (
    <div
      style={{
        padding: "12px",
        background: "var(--bg-tertiary)",
        borderRadius: "var(--radius-sm)",
        display: "flex",
        gap: "8px",
        alignItems: "center",
        flexWrap: "wrap",
      }}
    >
      <code
        style={{
          flex: "1 1 180px",
          minWidth: 0,
          fontFamily: "monospace",
          fontSize: "14px",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
        }}
      >
        {url}
      </code>
      <button
        onClick={onCopy}
        className="button"
        type="button"
        style={{ whiteSpace: "nowrap", padding: "6px 12px" }}
      >
        {copied ? t("buttons.copied") : t("buttons.copy")}
      </button>
    </div>
  );
}
