import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { ApiError, api } from "@/lib/api";

// Admin session cookie (P8): an opaque token whose SHA-256 the API stores.
export const SESSION_COOKIE = "ni_admin";

export const currentAdmin = cache(async (): Promise<string | null> => {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  try {
    return (await api.post<{ email: string }>("/api/admin/auth/session", { token })).email;
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 422)) return null;
    throw error;
  }
});

/** Server components, actions and route handlers under /console call this first. */
export async function requireAdmin(): Promise<string> {
  const email = await currentAdmin();
  if (!email) redirect("/login");
  return email;
}
