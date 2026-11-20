"use client";

import { useLanguage } from "@/contexts/LanguageContext";

export interface NodeData {
  name: string;
  status: "online" | "offline";
  panel_version: string;
  xray_version: string;
  uptime?: number;
  address?: string;
  port?: number;
  panel_base?: string;
  scheme?: string;
  base_path?: string;
}

function buildNodeUrl(
  address?: string,
  port?: number,
  panel_base?: string,
  scheme?: string,
  base_path?: string,
): string | undefined {
  if (panel_base) {
    if (panel_base.startsWith("http://") || panel_base.startsWith("https://")) {
      return panel_base.replace(/\/$/, "");
    }
  }
  if (!address) return undefined;
  const host =
    address.startsWith("http://") || address.startsWith("https://")
      ? new URL(address).hostname
      : address;
  const schemePart = scheme === "http" ? "http:" : "https:";
  const portPart = port ? `:${port}` : "";
  const basePathPart = base_path && base_path !== "/" ? base_path : "";
  return `${schemePart}//${host}${portPart}${basePathPart}`;
}

export interface NodeGridProps {
  nodes: NodeData[];
  mainNode?: NodeData;
  admin?: boolean;
}

export function NodeGrid({ nodes, mainNode, admin }: NodeGridProps) {
  const { t } = useLanguage();

  const formatUptimeLabel = (
    seconds: number | undefined,
  ): string | undefined => {
    if (!seconds) return undefined;
    const hours = Math.floor(seconds / 3600);
    const days = Math.floor(hours / 24);
    if (days > 0) return t("texts.duration_days", { days });
    return t("texts.uptime_hours", { hours });
  };

  const renderNodeCard = (node: NodeData, isFullWidth: boolean) => {
    const online = node.status === "online";
    const uptimeStr = formatUptimeLabel(node.uptime);
    const url = admin
      ? buildNodeUrl(
          node.address,
          node.port,
          node.panel_base,
          node.scheme,
          node.base_path,
        )
      : undefined;

    const cardStyle: React.CSSProperties = {
      padding: "20px",
      background: "var(--bg-tertiary)",
      borderRadius: "var(--radius-md)",
      border: `1px solid ${online ? "var(--success)" : "var(--danger)"}`,
      cursor: url ? "pointer" : "default",
      transition: "transform 0.15s ease, box-shadow 0.15s ease",
    };

    if (isFullWidth) {
      cardStyle.width = "100%";
      cardStyle.marginBottom = "16px";
    } else {
      cardStyle.marginBottom = "16px";
    }

    return (
      <div
        style={cardStyle}
        onMouseEnter={(e) => {
          if (url) {
            e.currentTarget.style.transform = "translateY(-2px)";
            e.currentTarget.style.boxShadow = "0 8px 24px rgba(0,0,0,0.25)";
          }
        }}
        onMouseLeave={(e) => {
          if (url) {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "none";
          }
        }}
      >
        <div
          style={{
            fontWeight: "400",
            marginBottom: "12px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span className={`activity-dot ${online ? "online" : "offline"}`} />
          <span style={{ color: "inherit" }}>{node.name}</span>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "13px",
            color: "var(--text-secondary)",
            marginBottom: "4px",
          }}
        >
          <span>{t("texts.3x_ui")}: {node.panel_version}</span>
          <span>{t("texts.xray_label")}: {node.xray_version}</span>
        </div>
        {uptimeStr && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: "13px",
              color: "var(--text-secondary)",
              marginTop: "4px",
            }}
          >
            <span></span>
            <span>{t("texts.uptime")}: {uptimeStr}</span>
          </div>
        )}
      </div>
    );
  };

  // Динамическая сетка:
  // - Если чётное количество узлов всего - все в одну сетку 2 в строку
  // - Если не чётное - первый (основной) на всю ширину, остальные по чётному количеству
  const totalNodes = mainNode ? nodes.length + 1 : nodes.length;
  const isEven = totalNodes % 2 === 0;

  return (
    <div style={{ marginBottom: "16px" }}>
      {mainNode && !isEven ? (
        // Не чётное общее количество - основной на всю ширину, остальные в сетке
        <>
          {renderNodeCard(mainNode, true)}
          {nodes.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  nodes.length >= 2 ? "repeat(2, 1fr)" : "1fr",
                gap: "16px",
              }}
            >
              {nodes.map((node) => renderNodeCard(node, false))}
            </div>
          )}
        </>
      ) : (
        // Чётное общее количество - все в одну сетку 2 в строку
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: "16px",
          }}
        >
          {mainNode ? renderNodeCard(mainNode, false) : null}
          {nodes.map((node) => renderNodeCard(node, false))}
        </div>
      )}
    </div>
  );
}
