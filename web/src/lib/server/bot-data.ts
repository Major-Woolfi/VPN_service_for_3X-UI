import "server-only";

import { getBotApiBase, UPSTREAM_TIMEOUT_MS } from "./bot-proxy";
import type {
  FeaturesResponse,
  StatsOverviewResponse,
  Tariff,
  TariffsResponse,
} from "../types";

const SERVER_TIMEOUT_MS = UPSTREAM_TIMEOUT_MS;

function describe(error: unknown): string {
  if (error instanceof Error) {

    const cause = (error as { cause?: unknown }).cause;
    const reason =
      cause instanceof Error
        ? `: ${cause.message}`
        : typeof cause === "string"
          ? `: ${cause}`
          : "";
    return `${error.message}${reason}`;
  }
  return String(error);
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

export async function getTariffsServer(): Promise<Tariff[]> {
  try {
    const data = await serverGet<TariffsResponse>("/tariffs");
    return data.tariffs || [];
  } catch (error) {

    console.error(
      `[bot-data] не удалось получить /tariffs: ${describe(error)}`,
    );
    return [];
  }
}

export async function getFeaturesServer(): Promise<FeaturesResponse | null> {
  try {
    return await serverGet<FeaturesResponse>("/config/features");
  } catch (error) {
    console.error(
      `[bot-data] не удалось получить /config/features: ${describe(error)}`,
    );
    return null;
  }
}

export async function getStatsServer(): Promise<StatsOverviewResponse | null> {
  try {
    return await serverGet<StatsOverviewResponse>("/stats/overview");
  } catch (error) {
    console.error(
      `[bot-data] не удалось получить /stats/overview: ${describe(error)}`,
    );
    return null;
  }
}
