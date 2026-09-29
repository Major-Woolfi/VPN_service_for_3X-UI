import "server-only";

import { getBotApiBase, UPSTREAM_TIMEOUT_MS } from "./bot-proxy";
import type {
  FeaturesResponse,
  StatsOverviewResponse,
  Tariff,
  TariffsResponse,
} from "../types";

/**
 * Запросы к боту из Server Component.
 *
 * Клиентские хелперы в lib/api.ts бьют в относительный `/api/bot/...`,
 * который существует только в браузере. На сервере такой fetch падает
 * ("Failed to parse URL"), и данные молча превращаются в пустые -
 * именно поэтому блок тарифов на главной не отображался.
 *
 * Здесь идём напрямую в апстрим по BOT_API_URL.
 */

const SERVER_TIMEOUT_MS = UPSTREAM_TIMEOUT_MS;

function describe(error: unknown): string {
  if (error instanceof Error) {
    // fetch к недоступному хосту теряет исходную причину в cause
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
    // Молчаливый return [] раньше скрывал поломку: блок тарифов просто
    // исчезал. Ошибку обязаны видеть в логах.
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
