import "server-only";

import { NextRequest, NextResponse } from "next/server";

import type { SanitizedUser } from "../types";

export const SESSION_COOKIE_NAME = "vpn_token";
export const UPSTREAM_TIMEOUT_MS = 12_000;
export const DEFAULT_SESSION_MAX_AGE = 30 * 24 * 60 * 60;

export function getBotApiBase(): string {
  return (process.env.BOT_API_URL || "http://localhost:2005/api/v1")
    .replace(/\/api\/v1\/?$/, "")
    .replace(/\/$/, "");
}

export function sanitizeApiPath(segments: string[]): string {
  const parts: string[] = [];
  for (const raw of segments) {
    const segment = decodeURIComponent(raw)
      .replace(/[^A-Za-z0-9_.\-~]/g, "")
      .replace(/\.{2,}/g, ".");
    if (segment && segment !== "." && segment !== "..") {
      parts.push(segment);
    }
  }
  return `/${parts.join("/")}`;
}

export function readSessionToken(request: NextRequest): string | null {
  const value = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  return value && value.trim() ? value : null;
}

// ВАЖНО: ResponseCookies.set в этой версии Next принимает атрибуты только
// в форме set(name, value, options) - объектная форма молча теряет
// HttpOnly/SameSite/Max-Age.
export function setSessionCookie(
  response: NextResponse,
  token: string,
  maxAge: number,
): void {
  response.cookies.set(SESSION_COOKIE_NAME, token, {
    path: "/",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge,
  });
}

export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set(SESSION_COOKIE_NAME, "", {
    path: "/",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 0,
  });
}

function extractUpstreamSession(
  response: Response,
): { token: string; maxAge: number } | { clear: true } | null {
  const setCookie =
    response.headers.get("set-cookie") ||
    (typeof response.headers.getSetCookie === "function"
      ? (response.headers.getSetCookie() || []).join(", ")
      : "");
  if (!setCookie) return null;

  const match = new RegExp(`(?:^|[;,]\\s*)${SESSION_COOKIE_NAME}=([^;,]*)`).exec(
    setCookie,
  );
  if (!match) return null;

  const value = decodeURIComponent(match[1] || "").trim();
  if (!value) return { clear: true };

  const maxAgeMatch = /(?:^|[;,]\s*)Max-Age=(-?\d+)/i.exec(setCookie);
  const maxAge = maxAgeMatch
    ? Math.abs(Number(maxAgeMatch[1]))
    : DEFAULT_SESSION_MAX_AGE;

  return { token: value, maxAge: maxAge || DEFAULT_SESSION_MAX_AGE };
}

async function readUpstreamBody(response: Response): Promise<{
  data: unknown;
  isJson: boolean;
}> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await response.json().catch(() => null);
    return { data, isJson: true };
  }
  const text = await response.text();
  return {
    data: text ? { error: text } : { error: response.statusText },
    isJson: false,
  };
}

export interface ProxyOptions {
  segments: string[];
  method: string;
  search: string;
  body: ArrayBuffer | undefined;
  contentType: string | null;
}

export interface ProxyResult {
  response: NextResponse;
  sessionLost: boolean;
  sessionRefreshed: boolean;
}

export async function proxyBotRequest(
  request: NextRequest,
  options: ProxyOptions,
): Promise<ProxyResult> {
  const path = sanitizeApiPath(options.segments);
  const token = readSessionToken(request);

  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.contentType) headers["Content-Type"] = options.contentType;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${getBotApiBase()}/api/v1${path}${options.search}`,
      {
        method: options.method,
        headers,
        body: options.body,
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      },
    );
  } catch (error) {
    const timedOut =
      error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError");
    return {
      response: NextResponse.json(
        {
          error: timedOut ? "bot_api_timeout" : "bot_api_unavailable",
          auth_expired: false,
        },
        { status: timedOut ? 504 : 503 },
      ),
      sessionLost: false,
      sessionRefreshed: false,
    };
  }

  const { data, isJson } = await readUpstreamBody(upstream);
  const upstreamSession = extractUpstreamSession(upstream);

  // 401 от бота при наличии cookie = сессия истекла или отозвана.
  // Публичные эндпоинты без cookie такого сигнала не дают.
  const sessionLost = upstream.status === 401 && Boolean(token);

  const payload =
    isJson && data !== null && typeof data === "object" && !Array.isArray(data)
      ? {
          ...(data as Record<string, unknown>),
          ...(sessionLost ? { auth_expired: true } : {}),
        }
      : data;

  const response = NextResponse.json(payload, { status: upstream.status });

  if (upstreamSession && "token" in upstreamSession) {
    setSessionCookie(response, upstreamSession.token, upstreamSession.maxAge);
    return {
      response,
      sessionLost,
      sessionRefreshed: true,
    };
  }

  if (upstreamSession || sessionLost) {
    clearSessionCookie(response);
  }

  return { response, sessionLost, sessionRefreshed: false };
}

export async function fetchServerProfile(
  token: string,
): Promise<SanitizedUser | null> {
  try {
    const response = await fetch(`${getBotApiBase()}/api/v1/profile`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    if (!response.ok) return null;
    const data = (await response.json().catch(() => null)) as SanitizedUser | null;
    return data && typeof data === "object" ? data : null;
  } catch {
    return null;
  }
}
