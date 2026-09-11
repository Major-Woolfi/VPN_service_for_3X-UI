'use client';

import { useLanguage } from '@/contexts/LanguageContext';

export interface NodeData {
  name: string;
  status: 'online' | 'offline';
  panel_version: string;
  xray_version: string;
  uptime?: number;
  address?: string;
  port?: number;
  panel_base?: string;
  scheme?: string;
  base_path?: string;
}

function formatUptime(seconds: number, t: (key: string, params?: Record<string, string | number>) => string): string {
  const hours = Math.floor(seconds / 3600);
  const days = Math.floor(hours / 24);
  if (days > 0) return t('texts.duration_days', { days });
  return t('texts.uptime_hours', { hours });
}

function buildNodeUrl(address?: string, port?: number, panel_base?: string, scheme?: string, base_path?: string): string | undefined {
  if (panel_base) {
    if (panel_base.startsWith('http://') || panel_base.startsWith('https://')) {
      return panel_base.replace(/\/$/, '');
    }
  }
  if (!address) return undefined;
  const host = address.startsWith('http://') || address.startsWith('https://') ? new URL(address).hostname : address;
  const schemePart = scheme === 'http' ? 'http:' : 'https:';
  const portPart = port ? `:${port}` : '';
  const basePathPart = base_path && base_path !== '/' ? base_path : '';
  return `${schemePart}//${host}${portPart}${basePathPart}`;
}

interface NodeCardProps {
  node: NodeData;
  admin?: boolean;
}

function NodeCard({ node, admin }: NodeCardProps) {
  const { t } = useLanguage();
  const online = node.status === 'online';
  const uptimeStr = node.uptime ? formatUptime(node.uptime, t) : '';
  const url = admin ? buildNodeUrl(node.address, node.port, node.panel_base, node.scheme, node.base_path) : undefined;

  const cardContent = (
    <div
      style={{
        padding: '20px',
        background: 'var(--bg-tertiary)',
        borderRadius: 'var(--radius-md)',
        border: `1px solid ${online ? 'var(--success)' : 'var(--danger)'}`,
        cursor: url ? 'pointer' : 'default',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
      }}
      onMouseEnter={(e) => {
        if (url) {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.25)';
        }
      }}
      onMouseLeave={(e) => {
        if (url) {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = 'none';
        }
      }}
    >
      <div style={{ fontWeight: '400', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span className={`activity-dot ${online ? 'online' : 'offline'}`} />
        <span style={{ color: 'inherit' }}>{node.name}</span>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
        <span>{t('texts.3x_ui')}: {node.panel_version}</span>
        <span>{t('texts.xray_label')}: {node.xray_version}</span>
      </div>
      {uptimeStr && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          <span></span>
          <span>{t('texts.uptime')}: {uptimeStr}</span>
        </div>
      )}
    </div>
  );

  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', color: 'inherit' }}>
        {cardContent}
      </a>
    );
  }

  return cardContent;
}

export interface NodeGridProps {
  nodes: NodeData[];
  mainNode?: NodeData;
  admin?: boolean;
}

export function NodeGrid({ nodes, mainNode, admin }: NodeGridProps) {
  const { t } = useLanguage();

  const renderMainNode = () => {
    if (!mainNode) return null;
    const online = mainNode.status === 'online';
    const uptimeStr = mainNode.uptime ? formatUptime(mainNode.uptime, t) : '';
    const url = admin ? buildNodeUrl(mainNode.address, mainNode.port, mainNode.panel_base, mainNode.scheme, mainNode.base_path) : undefined;

    const content = (
      <div
        style={{
          padding: '20px',
          background: 'var(--bg-tertiary)',
          borderRadius: 'var(--radius-md)',
          border: `1px solid ${online ? 'var(--success)' : 'var(--danger)'}`,
          cursor: url ? 'pointer' : 'default',
          transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        }}
        onMouseEnter={(e) => {
          if (url) {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.25)';
          }
        }}
        onMouseLeave={(e) => {
          if (url) {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = 'none';
          }
        }}
      >
        <div style={{ fontWeight: '400', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className={`activity-dot ${mainNode.status === 'online' ? 'online' : 'offline'}`} />
          <span style={{ color: 'inherit' }}>{mainNode.name}</span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
          <span>{t('texts.3x_ui')}: {mainNode.panel_version}</span>
          <span>{t('texts.xray_label')}: {mainNode.xray_version}</span>
        </div>
        {uptimeStr && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            <span></span>
            <span>{t('texts.uptime')}: {formatUptime(mainNode.uptime!, t)}</span>
          </div>
        )}
      </div>
    );

    if (url) {
      return (
        <a href={url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', color: 'inherit', display: 'block', marginBottom: '16px' }}>
          {content}
        </a>
      );
    }

    return <div style={{ marginBottom: '16px' }}>{content}</div>;
  };

  return (
    <div style={{ marginBottom: '16px' }}>
      {renderMainNode()}

      {nodes.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(auto-fit, minmax(${nodes.length % 2 === 0 ? '260px' : '280px'}, 1fr))`,
            gap: '16px',
          }}
        >
          {nodes.map((node) => (
            <NodeCard key={node.name} node={node} admin={admin} />
          ))}
        </div>
      )}
    </div>
  );
}
