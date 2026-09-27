import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE_NAME = "vpn_token";

const PROTECTED_ROOTS = [
  "/profile",
  "/settings",
  "/subscribe",
  "/client",
  "/referral",
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

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const authenticated = hasSessionCookie(request);

  // Server Component'ы (layout) читают путь, чтобы не устроить
  // петлю редиректов на гостевых страницах.
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
    const next = request.nextUrl.searchParams.get("next");
    const target =
      next && next.startsWith("/") && !next.startsWith("//") ? next : "/profile";
    return NextResponse.redirect(new URL(target, request.url));
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|_next/data|favicon.ico|icon.jpg|robots.txt|sitemap.txt|manifest.json|translations|api/bot|api/admin|api/session).*)",
  ],
};
