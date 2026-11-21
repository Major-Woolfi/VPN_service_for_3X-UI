import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/constants";
import { UPSTREAM_TIMEOUT_MS, getBotApiBase } from "@/lib/server/bot-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;

  if (token) {
    try {
      await fetch(`${getBotApiBase()}/api/v1/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      });
    } catch {
      // Сессия и так считается истёкшей - очищаем cookie в любом случае.
    }
  }

  const response = NextResponse.redirect(new URL("/login?reason=session_expired", request.url));
  response.headers.set("Cache-Control", "no-store");

  response.cookies.set(SESSION_COOKIE_NAME, "", {
    path: "/",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 0,
  });

  response.cookies.set("vpn_clear_cache", "1", {
    path: "/",
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60,
  });

  return response;
}
