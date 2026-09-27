import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE_NAME, UPSTREAM_TIMEOUT_MS, getBotApiBase } from "@/lib/server/bot-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Сессия на боте недействительна: чистим cookie и отправляем на вход.
// Вынесено в Route Handler, потому что Server Component не умеет удалять cookie.
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
      // Сессия уже недействительна на стороне бота - чистим только локально.
    }
  }

  const response = NextResponse.redirect(
    new URL("/login?reason=session_expired", request.url),
  );
  response.cookies.set(SESSION_COOKIE_NAME, "", {
    path: "/",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 0,
  });
  return response;
}
