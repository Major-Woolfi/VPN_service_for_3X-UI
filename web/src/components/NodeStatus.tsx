'use client';

import { useState, useEffect, useRef } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { fetchJson, API_BASE_URL, PANEL_STATUS_POLL_INTERVAL_MS, getAdminPanelStatus } from '@/lib/api';
import { NodeGrid, type NodeData } from '@/components/NodeGrid';

interface NodeStatusData {
  panel: {
    panel_version: string;
    xray_version: string;
    panel_base?: string;
  };
  server_status: Record<string, unknown>;
  nodes: Record<string, unknown>[];
}

function isOnlineFromState(ss: Record<string, unknown>): boolean {
  const xray = ss.xray as Record<string, unknown> | undefined;
  return typeof xray?.state === 'string' && xray.state === 'running';
}

export default function NodeStatus({ admin }: { admin?: boolean } = {}) {
  const [data, setData] = useState<NodeStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { t } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;
    const aborter = new AbortController();

    const fetchData = async () => {
      try {
        let json: NodeStatusData;
        if (admin) {
          json = await getAdminPanelStatus();
        } else {
          json = await fetchJson<NodeStatusData>(
            `${API_BASE_URL}/stats/panel-status`,
            { signal: aborter.signal },
          );
        }
        if (mounted) {
          setData(json);
          setError('');
          setLoading(false);
        }
      } catch {
        if (mounted) {
          setError(t('texts.node_status_failed'));
          setLoading(false);
        }
      }
    };

    fetchData();
    const interval = setInterval(fetchData, PANEL_STATUS_POLL_INTERVAL_MS);

    return () => {
      mounted = false;
      aborter.abort();
      clearInterval(interval);
    };
  }, [admin, t]);

  if (loading) {
    return <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>{t('texts.loading_nodes')}</p>;
  }

  if (error) {
    return (
      <p style={{ color: 'var(--danger)', fontSize: '14px' }}>
        {t('texts.node_status_failed')}
      </p>
    );
  }

  if (!data?.nodes?.length) {
    return (
      <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
        {t('texts.nodes_empty')}
      </p>
    );
  }

  const nodes: Record<string, unknown>[] = Array.isArray(data.nodes) ? data.nodes : [];
  const ss = data.server_status as Record<string, unknown> | undefined;
  const mainOnline = ss ? isOnlineFromState(ss) : false;

  const mainServerCountry = process.env.NEXT_PUBLIC_MAIN_SERVER_COUNTRY || '';

  const mainNode: NodeData = {
    name: `${mainServerCountry ? `${mainServerCountry} ` : ''}${t('texts.main_server')}`.trim(),
    status: mainOnline ? 'online' : 'offline',
    panel_version: data.panel?.panel_version || '-',
    xray_version: data.panel?.xray_version || '-',
    uptime: typeof ss?.uptime === 'number' ? ss.uptime : undefined,
    panel_base: admin ? data.panel?.panel_base : undefined,
  };

  const otherNodes: NodeData[] = nodes.map((node, idx) => {
    const name = String(node.name || node.node_name || `${t('texts.node_fallback')} ${idx + 1}`);
    const status = String(node.status || 'offline');
    const uptime = typeof node.uptime === 'number' ? node.uptime : typeof node.uptime === 'string' ? parseInt(node.uptime, 10) : NaN;

    return {
      name,
      status: status as 'online' | 'offline',
      panel_version: String(node.panel_version || node.version || data.panel?.panel_version || '-'),
      xray_version: String(node.xray_version || '-'),
      uptime: Number.isFinite(uptime) ? uptime : undefined,
      address: typeof node.address === 'string' ? node.address : undefined,
      port: typeof node.port === 'number' ? node.port : typeof node.port === 'string' ? parseInt(node.port, 10) : undefined,
      scheme: typeof node.scheme === 'string' ? node.scheme : undefined,
      base_path: typeof node.basePath === 'string' ? node.basePath : typeof node.base_path === 'string' ? node.base_path : undefined,
    };
  });

  return (
    <div ref={containerRef} style={{ marginTop: '16px' }}>
      <div style={{ fontWeight: '600', fontSize: '14px', marginBottom: '12px' }}>{t('texts.nodes')}</div>
      <NodeGrid mainNode={mainNode} nodes={otherNodes} admin={admin} />
    </div>
  );
}

