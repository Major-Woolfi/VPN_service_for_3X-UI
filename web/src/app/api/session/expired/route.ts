import { NextResponse, type NextRequest } from "next/server";

import {
  SESSION_COOKIE_NAME,
  UPSTREAM_TIMEOUT_MS,
  getBotApiBase,
} from "@/lib/server/bot-proxy";

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

    }
  }

  const response = NextResponse.redirect(
    new URL("/login?reason=session_expired", request.url),
  );

  const host = request.headers.get("host") || "";
  const domain = host.split(":")[0];
  const isIp = /^\d{1,3}(\.\d{1,3}){3}$/.test(domain);

  for (const opts of isIp
    ? [{ path: "/" }]
    : [{ path: "/" }, { path: "/", domain }]) {
    response.cookies.set(SESSION_COOKIE_NAME, "", {
      ...opts,
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: 0,
    });
  }

  response.cookies.set("vpn_clear_cache", "1", {
    path: "/",
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60,
  });

  return response;
}
