import { type NextRequest, NextResponse } from "next/server";

// Optimistic check only: without the session cookie, /console goes to the login page.
// The console layout, actions and routes still verify the session with the API.
export function proxy(request: NextRequest) {
  if (!request.cookies.has("ni_admin")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/console", "/console/:path*"],
};
