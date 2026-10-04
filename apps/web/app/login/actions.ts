"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { SESSION_COOKIE } from "@/lib/session";

export interface LoginState {
  sent: boolean;
  error?: string;
}

export async function requestLogin(_: LoginState, form: FormData): Promise<LoginState> {
  const email = String(form.get("email") ?? "").trim();
  if (!email.includes("@") || email.length > 320) return { sent: false, error: "이메일 주소를 확인하세요." };
  await api.post("/api/admin/auth/request", { email });
  // Same answer for every address: the page never reveals which one is the admin's.
  return { sent: true };
}

export async function completeLogin(form: FormData): Promise<void> {
  const token = String(form.get("token") ?? "");
  let session: { token: string; expires_at: string };
  try {
    session = await api.post<{ token: string; expires_at: string }>("/api/admin/auth/verify", { token });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 422)) redirect("/login?error=expired");
    throw error;
  }
  (await cookies()).set(SESSION_COOKIE, session.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    expires: new Date(session.expires_at),
  });
  redirect("/console");
}

export async function logout(): Promise<void> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (token) await api.post("/api/admin/auth/logout", { token }).catch(() => undefined);
  store.delete(SESSION_COOKIE);
  redirect("/");
}
