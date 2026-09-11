'use client';

import { useMemo } from 'react';
import type { Tariff } from '@/lib/types';
import { useLanguage } from '@/contexts/LanguageContext';

function getRowConfigs(count: number): number[][] {
  if (count === 0) return [];
  const rows: number[][] = [];
  let remaining = count;

  while (remaining > 0) {
    if (remaining <= 3) {
      rows.push([remaining]);
      break;
    }

    if (remaining % 3 === 0) {
      rows.push([3]);
      remaining -= 3;
    } else if (remaining % 3 === 1) {
      if (rows.length > 0) {
        rows[rows.length - 1][0] -= 1;
        rows.push([2]);
        rows.push([2]);
        remaining = 0;
        break;
      } else {
        rows.push([2]);
        remaining -= 2;
      }
    } else {
      rows.push([3]);
      remaining -= 3;
    }
  }

  return rows;
}

export default function TariffGrid({ tariffs, onSelect }: { tariffs: Tariff[]; onSelect?: (tariff: Tariff) => void }) {
  const { t } = useLanguage();
  const rows = useMemo(() => getRowConfigs(tariffs.length), [tariffs.length]);

  const tariffRows = useMemo(() => {
    const result: Tariff[][] = [];
    let index = 0;
    for (const cols of rows) {
      result.push(tariffs.slice(index, index + cols[0]));
      index += cols[0];
    }
    return result;
  }, [tariffs, rows]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {tariffRows.map((rowTariffs, rowIdx) => (
        <div
          key={rowIdx}
          className={`tariff-row tariff-row-cols-${rowTariffs.length}`}
        >
          {rowTariffs.map((tariff) => (
            <div
              key={tariff.id}
              className="card tariff-card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                padding: '20px',
                cursor: onSelect ? 'pointer' : 'default',
              }}
              onClick={() => onSelect?.(tariff)}
            >
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontWeight: 600, fontSize: '16px' }}>{tariff.name}</div>
                <div className="text-secondary" style={{ fontSize: '13px', marginTop: '4px' }}>
                  {t('texts.traffic_gb', { value: tariff.traffic_gb })} · {tariff.ip_limit} {t('texts.ip_label')} · {t('texts.duration_days', { days: tariff.duration_days })}
                </div>
                {tariff.locations.length > 0 && (
                  <div className="text-secondary" style={{ fontSize: '13px', marginTop: '4px' }}>
                    {tariff.locations.join(', ')}
                  </div>
                )}
              </div>
              <div style={{ fontWeight: 700, color: 'var(--accent)', fontSize: '18px', marginTop: '12px' }}>
                {tariff.price_rub} ₽
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

