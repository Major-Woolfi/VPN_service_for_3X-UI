import "server-only";

import { cache } from "react";
import { getBotApiBase, UPSTREAM_TIMEOUT_MS } from "./bot-proxy";
import type { FeaturesResponse, StatsOverviewResponse, TariffsResponse } from "../types";

const SERVER_TIMEOUT_MS = UPSTREAM_TIMEOUT_MS;

function describeError(err: unknown): string {
  if (err instanceof Error) {
    const cause = (err as { cause?: unknown }).cause;
    const reason =
      cause instanceof Error ? `: ${cause.message}` : typeof cause === "string" ? `: ${cause}` : "";
    return `${err.message}${reason}`;
  }
  return String(err);
}

async function serverGet<T>(path: string): Promise<T> {
  const response = await fetch(`${getBotApiBase()}/api/v1${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(SERVER_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`bot api ${path} -> ${response.status}`);
  }
  return (await response.json()) as T;
}

export const getTariffsServer = cache(async (): Promise<TariffsResponse> => {
  try {
    const data = await serverGet<TariffsResponse>("/tariffs");
    return { tariffs: data.tariffs || [], tariff_mode: data.tariff_mode };
  } catch (err) {
    console.error(`[bot-data] не удалось получить /tariffs: ${describeError(err)}`);
    return { tariffs: [] };
  }
});

export const getFeaturesServer = cache(async (): Promise<FeaturesResponse | null> => {
  try {
    return await serverGet<FeaturesResponse>("/config/features");
  } catch (err) {
    console.error(`[bot-data] не удалось получить /config/features: ${describeError(err)}`);
    return null;
  }
});

export async function getStatsOverviewServer(): Promise<StatsOverviewResponse | null> {
  try {
    return await serverGet<StatsOverviewResponse>("/stats/overview");
  } catch (err) {
    console.error(`[bot-data] не удалось получить /stats/overview: ${describeError(err)}`);
    return null;
  }
}
