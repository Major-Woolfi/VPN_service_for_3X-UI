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

export interface NodeGridProps {
  nodes: NodeData[];
  mainNode?: NodeData;
  admin?: boolean;
}

function normalizeUrl(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  try {
    const url = new URL(raw);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

function nodePanelUrl(node: NodeData): string | undefined {
  const direct = normalizeUrl(node.panel_base);
  if (direct) return direct;
  if (!node.address) return undefined;

  const scheme = node.scheme === "http" ? "http" : "https";
  const host =
    node.address.includes(":") && !node.address.startsWith("[")
      ? `[${node.address}]`
      : node.address;
  const port = node.port ? `:${node.port}` : "";
  const basePath = (node.base_path || "").trim();
  const path = basePath ? (basePath.startsWith("/") ? basePath : `/${basePath}`) : "/";
  const suffix = path.endsWith("/") ? path : `${path}/`;
  return normalizeUrl(`${scheme}://${host}${port}${suffix}`);
}

export function NodeGrid({ nodes, mainNode, admin = false }: NodeGridProps) {
  const { t } = useLanguage();

  const formatUptimeLabel = (seconds: number | undefined): string | undefined => {
    if (!seconds) return undefined;
    const hours = Math.floor(seconds / 3600);
    const days = Math.floor(hours / 24);
    if (days > 0) return t("texts.duration_days", { days });
    return t("texts.uptime_hours", { hours });
  };

  const renderNodeCard = (node: NodeData, isMain = false) => {
    const online = node.status === "online";
    const uptimeStr = formatUptimeLabel(node.uptime);
    const href = admin ? nodePanelUrl(node) : undefined;
    const className = [
      "node-card",
      online ? "node-card--online" : "node-card--offline",
      isMain ? "node-card--main" : "",
      href ? "node-card--link" : "",
    ]
      .filter(Boolean)
      .join(" ");

    const content = (
      <>
        <div className="node-card__header">
          <span className={`activity-dot ${online ? "online" : "offline"}`} />
          <span className="node-card__name">{node.name}</span>
          {href && (
            <span className="node-card__open" title={t("texts.open_node_panel")} aria-hidden="true">
              ↗
            </span>
          )}
        </div>
        <div className="node-card__meta">
          <span>
            {t("texts.3x_ui")}: {node.panel_version || "-"}
          </span>
          <span>
            {t("texts.xray_label")}: {node.xray_version || "-"}
          </span>
          {uptimeStr && (
            <span>
              {t("texts.uptime")}: {uptimeStr}
            </span>
          )}
        </div>
      </>
    );

    if (href) {
      return (
        <button
          key={node.name}
          type="button"
          className={className}
          onClick={() => window.open(href, "_blank", "noopener,noreferrer")}
          title={t("texts.open_node_panel")}
          aria-label={`${node.name} - ${t("texts.open_node_panel")}`}
        >
          {content}
        </button>
      );
    }

    return (
      <div key={node.name} className={className}>
        {content}
      </div>
    );
  };

  return (
    <div className="node-stack">
      {mainNode ? renderNodeCard(mainNode, true) : null}
      {nodes.length > 0 ? (
        <div className="node-list">{nodes.map((node) => renderNodeCard(node))}</div>
      ) : null}
    </div>
  );
}
