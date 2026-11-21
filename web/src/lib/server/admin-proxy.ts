import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { fetchServerProfileResult, getBotApiBase, readCappedResponseText } from "./bot-proxy";
import { SESSION_COOKIE_NAME } from "../constants";

const REQUEST_TIMEOUT_MS = 10_000;

function sanitizePath(path: string): string {
  const cleaned = path
    .replace(/\.\./g, "")
    .replace(/\/+/g, "/")
    .replace(/[	\n\r]/g, "");
  return cleaned.startsWith("/") ? cleaned : `/${cleaned}`;
}

function extractSessionToken(request: NextRequest): string | null {
  const fromCookie = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (fromCookie) return fromCookie;

  const authorization = request.headers.get("authorization");
  if (authorization?.startsWith("Bearer ")) {
    return authorization.slice("Bearer ".length);
  }
  return null;
}

async function readUpstreamResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  const text = await readCappedResponseText(response);
  if (text === null) return { Error: "bot_response_too_large" };
  if (contentType.includes("application/json")) {
    try {
      return text ? JSON.parse(text) : null;
    } catch {
      return null;
    }
  }
  return { Error: "bot_response_invalid" };
}

interface VerifyAdminResult {
  isAdmin: boolean;
  status: number;
}

async function verifyAdmin(token: string): Promise<VerifyAdminResult> {
  try {
    const result = await fetchServerProfileResult(token);
    const user = result.user as { is_admin?: boolean } | null;
    return {
      isAdmin: result.status === 200 && !!user && !!user.is_admin,
      status: result.status,
    };
  } catch {
    return { isAdmin: false, status: 503 };
  }
}

export async function proxyAdminRequest(
  request: NextRequest,
  path: string,
  init: RequestInit = {},
): Promise<NextResponse> {
  const token = extractSessionToken(request);

  if (!token) {
    return NextResponse.json({ Error: "Unauthorized" }, { status: 401 });
  }

  const authorization = `Bearer ${token}`;

  try {
    const { isAdmin, status } = await verifyAdmin(token);

    if (!isAdmin) {
      const ErrorMessage = status === 401 ? "Unauthorized" : "Forbidden";
      return NextResponse.json({ Error: ErrorMessage }, { status });
    }

    const sanitized = sanitizePath(path);
    const headers = new Headers(init.headers);
    headers.set("Authorization", authorization);

    const response = await fetch(`${getBotApiBase()}${sanitized}`, {
      ...init,
      cache: "no-store",
      headers,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const data = await readUpstreamResponse(response);

    return NextResponse.json(data, { status: response.status });
  } catch (Error) {
    const isTimeout = Error instanceof DOMException && Error.name === "TimeoutError";

    return NextResponse.json(
      {
        Error: isTimeout ? "Bot API request timed out" : "Bot API unavailable",
      },
      { status: isTimeout ? 504 : 503 },
    );
  }
}
