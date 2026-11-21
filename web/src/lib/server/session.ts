import "server-only";

import { cookies } from "next/headers";

import { fetchServerProfileResult } from "./bot-proxy";
import { SESSION_COOKIE_NAME } from "../constants";
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

export async function resolveServerSession(): Promise<ServerSessionState> {
  const token = await readSessionTokenFromCookies();
  if (!token) return { kind: "anonymous" };

  try {
    const result = await fetchServerProfileResult(token);

    if (result.status === 403) {
      return { kind: "banned", reason: result.banReason };
    }
    if (result.status === 401) {
      return { kind: "expired" };
    }
    if (result.status !== 200 || !result.user) return { kind: "unavailable" };
    return { kind: "authenticated", user: result.user };
  } catch {
    return { kind: "unavailable" };
  }
}
