"use client";

import TariffGrid from "./TariffGrid";
import { useRouter } from "next/navigation";
import type { Tariff } from "@/lib/types";

export default function TariffGridClient({
  tariffs,
  tariffMode,
}: {
  tariffs: Tariff[];
  tariffMode?: "old" | "new";
}) {
  const router = useRouter();

  return (
    <TariffGrid
      tariffs={tariffs}
      tariffMode={tariffMode}
      onSelect={(tariff) => {
        router.push(`/subscribe?tariff=${tariff.id}`);
      }}
    />
  );
}
