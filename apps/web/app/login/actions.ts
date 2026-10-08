"use server";

import { redirect } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { LOGIN_MESSAGES, type LoginOutcome, type SessionUser, forgetSession, safeNext } from "@/lib/auth";
import { clearSessionCookie, clientHeaders, sessionToken, setSessionCookie } from "@/lib/session";

export interface LoginState {
  error?: string;
  outcome?: LoginOutcome;
  username?: string;
}

interface SessionOut {
  token: string;
  expires_at: string;
  user: SessionUser;
}

function outcomeOf(error: ApiError): LoginOutcome {
  if (error.status === 429) return "throttled";
  if (error.status === 403) {
    try {
      const outcome = (JSON.parse(error.message) as { outcome?: string }).outcome;
      if (outcome === "pending" || outcome === "rejected" || outcome === "suspended") return outcome;
    } catch {
      // fall through: an unexpected body is treated as a failed login
    }
  }
  return "invalid";
}

export async function login(_: LoginState, form: FormData): Promise<LoginState> {
  const username = String(form.get("username") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (!username || !password) return { error: "아이디와 비밀번호를 입력하세요.", username };
  let session: SessionOut;
  try {
    session = await api.post<SessionOut>(
      "/api/admin/accounts/login",
      { username: username.slice(0, 64), password: password.slice(0, 256) },
      await clientHeaders(),
    );
  } catch (error) {
    if (!(error instanceof ApiError) || error.status >= 500) throw error;
    const outcome = outcomeOf(error);
    return { error: LOGIN_MESSAGES[outcome], outcome, username };
  }
  await setSessionCookie(session.token, session.expires_at);
  redirect(session.user.must_change_password ? "/change-password" : safeNext(form.get("next")));
}

export async function logout(): Promise<void> {
  const token = await sessionToken();
  forgetSession(token);
  if (token) await api.post("/api/admin/accounts/logout", { token }, await clientHeaders()).catch(() => undefined);
  await clearSessionCookie();
  redirect("/login");
}
