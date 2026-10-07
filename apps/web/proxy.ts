import { type NextRequest, NextResponse } from "next/server";

import { AuthUnavailable, SESSION_COOKIE, lookupSession } from "@/lib/auth";

const FORCED_CHANGE = "/change-password";

// Every page, client navigation, route handler and server action passes here (plan 14): the
// session is checked with the API on each request, so a revoked or suspended account stops at
// once. Pages, actions and route handlers still check again (lib/session.ts).
export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  let user;
  try {
    user = await lookupSession(request.cookies.get(SESSION_COOKIE)?.value);
  } catch (error) {
    if (!(error instanceof AuthUnavailable)) throw error;
    return new NextResponse("인증 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.", { status: 503 });
  }
  if (!user) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new NextResponse("로그인이 필요합니다.", { status: 401 });
    }
    const login = new URL("/login", request.url);
    if (pathname !== "/") login.searchParams.set("next", pathname + search);
    const response = NextResponse.redirect(login);
    if (request.cookies.has(SESSION_COOKIE)) response.cookies.delete(SESSION_COOKIE);
    return response;
  }
  if (user.must_change_password && pathname !== FORCED_CHANGE) {
    return NextResponse.redirect(new URL(FORCED_CHANGE, request.url));
  }
  if (user.role !== "admin" && (pathname === "/console" || pathname.startsWith("/console/"))) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Everything except static assets, the login and sign-up pages, and /internal (cache hooks
  // reached over the compose network with the console key; Caddy answers 404 from outside).
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico|icon\\.svg|login$|signup$|internal/).*)"],
};
