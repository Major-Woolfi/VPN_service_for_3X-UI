import "server-only";

import { cookies } from "next/headers";

import {
  SESSION_COOKIE_NAME,
  UPSTREAM_TIMEOUT_MS,
  getBotApiBase,
} from "./bot-proxy";
import type { SanitizedUser } from "../types";

export { SESSION_COOKIE_NAME };

export async function readSessionTokenFromCookies(): Promise<string | null> {
  const store = await cookies();
  const value = store.get(SESSION_COOKIE_NAME)?.value;
  return value && value.trim() ? value : null;
}

export type ServerSessionState =
  | { kind: "anonymous" }
  | { kind: "authenticated"; user: SanitizedUser }
  | { kind: "expired" }
  | { kind: "banned"; reason: string }
  | { kind: "unavailable" };

// Сессия проверяется на сервере: cookie есть, но профиль не отдаётся -
// значит токен истёк или был отозван, и разлогинивать нужно сразу.
export async function resolveServerSession(): Promise<ServerSessionState> {
  const token = await readSessionTokenFromCookies();
  if (!token) return { kind: "anonymous" };

  try {
    const response = await fetch(`${getBotApiBase()}/api/v1/profile`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    // 403 от бота - это бан аккаунта, а не истёкшая сессия.
    // Разлогинивать забаненного нельзя: он должен увидеть причину.
    if (response.status === 403) {
      const data = (await response.json().catch(() => null)) as {
        ban_reason?: unknown;
      } | null;
      const reason =
        data && typeof data.ban_reason === "string" ? data.ban_reason : "";
      return { kind: "banned", reason };
    }
    if (response.status === 401) {
      return { kind: "expired" };
    }
    if (!response.ok) return { kind: "unavailable" };
    const data = (await response
      .json()
      .catch(() => null)) as SanitizedUser | null;
    if (data && typeof data === "object") {
      return { kind: "authenticated", user: data };
    }
    return { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
}
