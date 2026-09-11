'use client';

import TariffGrid from './TariffGrid';
import { useRouter } from 'next/navigation';
import type { Tariff } from '@/lib/types';

export default function TariffGridClient({ tariffs }: { tariffs: Tariff[] }) {
  const router = useRouter();

  return (
    <TariffGrid
      tariffs={tariffs}
      onSelect={(tariff) => {
        router.push(`/subscribe?tariff=${tariff.id}`);
      }}
    />
  );
}

