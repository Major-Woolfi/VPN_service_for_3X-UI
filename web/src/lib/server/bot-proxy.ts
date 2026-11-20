import "server-only";

import { createHash } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import type { SanitizedUser } from "../types";

export const SESSION_COOKIE_NAME = "vpn_token";
export const UPSTREAM_TIMEOUT_MS = 12_000;
export const DEFAULT_SESSION_MAX_AGE = 30 * 24 * 60 * 60;
export const MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024;
const MAX_UPSTREAM_RESPONSE_BYTES = 5 * 1024 * 1024;
const PROFILE_CACHE_TTL_MS = 3_000;
const PROFILE_CACHE_MAX_ENTRIES = 1_000;

export function getBotApiBase(): string {
  return (process.env.BOT_API_URL || "http://localhost:2005/api/v1")
    .replace(/\/api\/v1\/?$/, "")
    .replace(/\/$/, "");
}

export function sanitizeApiPath(segments: string[]): string {
  const starts: string[] = [];
  for (const raw of segments) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(raw);
    } catch {
      continue;
    }
    const segment = decoded
      .replace(/[^A-Za-z0-9_.\-~]/g, "")
      .replace(/\.{2,}/g, ".");
    if (segment && segment !== "." && segment !== "..") {
      starts.push(segment);
    }
  }
  return `/${starts.join("/")}`;
}

export function readSessionToken(request: NextRequest): string | null {
  const value = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  return value && value.trim() ? value : null;
}

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

  const match = new RegExp(
    `(?:^|[;,]\\s*)${SESSION_COOKIE_NAME}=([^;,]*)`,
  ).exec(setCookie);
  if (!match) return null;

  let value: string;
  try {
    value = decodeURIComponent(match[1] || "").trim();
  } catch {
    return { clear: true };
  }
  if (!value) return { clear: true };

  const maxAgeMatch = /(?:^|[;,]\s*)Max-Age=(-?\d+)/i.exec(setCookie);
  const rawMaxAge = maxAgeMatch
    ? Number(maxAgeMatch[1])
    : DEFAULT_SESSION_MAX_AGE;
  if (rawMaxAge <= 0) return { clear: true };

  return { token: value, maxAge: rawMaxAge || DEFAULT_SESSION_MAX_AGE };
}

export async function readCappedResponseText(
  response: Response,
): Promise<string | null> {
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_UPSTREAM_RESPONSE_BYTES) {
    return null;
  }
  const body = response.body;
  if (!body) return "";
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    text += decoder.decode(value, { stream: true });
    if (text.length > MAX_UPSTREAM_RESPONSE_BYTES) {
      await reader.cancel();
      return null;
    }
  }
  return text + decoder.decode();
}

async function readUpstreamBody(response: Response): Promise<{
  data: unknown;
  isJson: boolean;
}> {
  const contentType = response.headers.get("content-type") || "";
  const text = await readCappedResponseText(response);
  if (text === null) {
    return { data: { Error: "bot_response_too_large" }, isJson: true };
  }
  if (contentType.includes("application/json")) {
    let data: unknown = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }
    return { data, isJson: true };
  }
  return {
    data: text ? { Error: text } : { Error: response.statusText },
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
  sessionHost: boolean;
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
  const forwardedFor =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    request.headers.get("x-real-ip")?.trim();
  if (forwardedFor) headers["X-Forwarded-For"] = forwardedFor;

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
  } catch (err) {
    const timedOut =
      err instanceof DOMException &&
      (err.name === "TimeoutError" || err.name === "AbortError");
    return {
      response: NextResponse.json(
        {
          Error: timedOut ? "bot_api_timeout" : "bot_api_unavailable",
          auth_expired: false,
        },
        { status: timedOut ? 504 : 503 },
      ),
      sessionHost: false,
      sessionRefreshed: false,
    };
  }

  const { data, isJson } = await readUpstreamBody(upstream);
  const upstreamSession = extractUpstreamSession(upstream);

  const sessionHost = upstream.status === 401 && Boolean(token);

  const payload =
    isJson && data !== null && typeof data === "object" && !Array.isArray(data)
      ? {
          ...(data as Record<string, unknown>),
          ...(sessionHost ? { auth_expired: true } : {}),
        }
      : data;

  const response = NextResponse.json(payload, { status: upstream.status });

  if (upstreamSession && "token" in upstreamSession) {
    setSessionCookie(response, upstreamSession.token, upstreamSession.maxAge);
    return {
      response,
      sessionHost,
      sessionRefreshed: true,
    };
  }

  if (upstreamSession || sessionHost) {
    clearSessionCookie(response);
  }

  return { response, sessionHost, sessionRefreshed: false };
}

export interface ServerProfileResult {
  user: SanitizedUser | null;
  status: number;
  banReason: string;
}

const profileCache = new Map<string, { expires: number; result: ServerProfileResult }>();

function parseBanReason(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const reason = (payload as { ban_reason?: unknown }).ban_reason;
  return typeof reason === "string" ? reason : "";
}

export async function fetchServerProfileResult(
  token: string,
): Promise<ServerProfileResult> {
  const key = createHash("sha256").update(token).digest("hex");
  const cached = profileCache.get(key);
  if (cached && cached.expires > Date.now()) return cached.result;

  const unavailable: ServerProfileResult = { user: null, status: 503, banReason: "" };
  try {
    const response = await fetch(`${getBotApiBase()}/api/v1/profile`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const payload = (await response.json().catch(() => null)) as unknown;
    const user =
      response.ok && payload && typeof payload === "object"
        ? (payload as SanitizedUser)
        : null;
    const result: ServerProfileResult = {
      user,
      status: response.status,
      banReason: response.status === 403 ? parseBanReason(payload) : "",
    };
    if (profileCache.size >= PROFILE_CACHE_MAX_ENTRIES) {
      const now = Date.now();
      for (const [cacheKey, entry] of profileCache) {
        if (entry.expires <= now) profileCache.delete(cacheKey);
      }
    }
    profileCache.set(key, { expires: Date.now() + PROFILE_CACHE_TTL_MS, result });
    return result;
  } catch {
    return unavailable;
  }
}

export async function fetchServerProfile(
  token: string,
): Promise<SanitizedUser | null> {
  return (await fetchServerProfileResult(token)).user;
}


