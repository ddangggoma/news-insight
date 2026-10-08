import "server-only";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { SESSION_COOKIE, type SessionUser, lookupSession } from "@/lib/auth";

export { SESSION_COOKIE };

export const currentUser = cache(async (): Promise<SessionUser | null> => {
  return lookupSession((await cookies()).get(SESSION_COOKIE)?.value);
});

/** Pages, actions and route handlers call this first; proxy.ts has already checked the session. */
export async function requireUser(): Promise<SessionUser> {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (user.must_change_password) redirect("/change-password");
  return user;
}

/** Console pages, actions and routes: admins only. */
export async function requireAdmin(): Promise<SessionUser> {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  return user;
}

export async function sessionToken(): Promise<string> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? "";
}

/** The browser's address and user agent for the API's rate limits and audit trail. */
export async function clientHeaders(): Promise<Record<string, string>> {
  const incoming = await headers();
  // Caddy is the only way in and sets X-Forwarded-For to the connecting address
  const ip = incoming.get("x-forwarded-for")?.split(",")[0]?.trim();
  const agent = incoming.get("user-agent")?.slice(0, 200);
  return { ...(ip ? { "X-Client-IP": ip } : {}), ...(agent ? { "X-Client-UA": agent } : {}) };
}

export async function setSessionCookie(token: string, expiresAt: string): Promise<void> {
  // Secure only when the request came over HTTPS: the site is also served over plain HTTP
  // (Caddy's HTTP port, 2026-10-06), where a Secure cookie would never be stored.
  const https = (await headers()).get("x-forwarded-proto") === "https";
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production" && https,
    sameSite: "lax",
    path: "/",
    expires: new Date(expiresAt),
  });
}

export async function clearSessionCookie(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
