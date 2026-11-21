import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/constants";

const PROTECTED_ROOTS = [
  "/profile",
  "/settings",
  "/subscribe",
  "/client",
  "/referral",
  "/co-owners",
  "/admin",
];

const GUEST_ONLY_PATHS = ["/login", "/register"];

function hasSessionCookie(request: NextRequest): boolean {
  const value = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  return Boolean(value && value.trim());
}

function buildLoginUrl(request: NextRequest): URL {
  const url = new URL("/login", request.url);
  const next = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  if (next && next !== "/") {
    url.searchParams.set("next", next);
  }
  const reason = request.nextUrl.searchParams.get("reason");
  if (reason) {
    url.searchParams.set("reason", reason);
  }
  return url;
}

function getSafeNextTarget(request: NextRequest): string {
  const next = request.nextUrl.searchParams.get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
    return "/profile";
  }
  const origin = request.nextUrl.origin;
  const target = new URL(next, origin);
  if (target.origin !== origin) {
    return "/profile";
  }
  return `${target.pathname}${target.search}${target.hash}`;
}

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const authenticated = hasSessionCookie(request);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-pathname", pathname);

  const isProtected = PROTECTED_ROOTS.some(
    (root) => pathname === root || pathname.startsWith(`${root}/`),
  );

  if (isProtected && !authenticated) {
    return NextResponse.redirect(buildLoginUrl(request));
  }

  const isGuestOnly = GUEST_ONLY_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  if (isGuestOnly && authenticated) {
    const reason = request.nextUrl.searchParams.get("reason");
    if (reason === "session_expired" || reason === "banned") {
      return NextResponse.next({ request: { headers: requestHeaders } });
    }
    return NextResponse.redirect(new URL(getSafeNextTarget(request), request.url));
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|_next/data|favicon.ico|icon.jpg|robots.txt|sitemap.txt|manifest.json|translations|api/bot|api/admin|api/session).*)",
  ],
};
