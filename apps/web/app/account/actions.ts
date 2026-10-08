"use server";

import { redirect } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import type { SessionUser } from "@/lib/auth";
import { clientHeaders, currentUser, sessionToken, setSessionCookie } from "@/lib/session";

export interface PasswordState {
  errors?: Partial<Record<"current" | "password" | "confirm" | "form", string>>;
}

export async function changePassword(_: PasswordState, form: FormData): Promise<PasswordState> {
  // not requireUser(): a user with a temporary password lands here and must get through
  if (!(await currentUser())) redirect("/login");
  const current = String(form.get("current") ?? "");
  const password = String(form.get("password") ?? "");
  if (!current) return { errors: { current: "현재 비밀번호를 입력하세요." } };
  if (password !== String(form.get("confirm") ?? "")) return { errors: { confirm: "새 비밀번호가 서로 다릅니다." } };
  let session: { token: string; expires_at: string; user: SessionUser };
  try {
    session = await api.post(
      "/api/admin/accounts/password",
      { token: await sessionToken(), current: current.slice(0, 256), password: password.slice(0, 256) },
      await clientHeaders(),
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/login");
    if (error.status === 400) {
      const detail = (JSON.parse(error.message) as { detail: { field: string | null; message: string } }).detail;
      const field = detail.field === "current" ? "current" : detail.field === "password" ? "password" : "form";
      return { errors: { [field]: detail.message } };
    }
    throw error;
  }
  await setSessionCookie(session.token, session.expires_at);
  redirect("/account?changed=1");
}

export async function logoutOthers(): Promise<void> {
  if (!(await currentUser())) redirect("/login");
  await api.post("/api/admin/accounts/logout-others", { token: await sessionToken() }, await clientHeaders());
  redirect("/account?others=1");
}
