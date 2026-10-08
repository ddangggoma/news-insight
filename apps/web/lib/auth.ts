// Shared by proxy.ts and server code, so no "server-only" here: nothing in this file runs in the browser.

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";

// Site session cookie (plan 14): an opaque token whose SHA-256 the API stores.
export const SESSION_COOKIE = "ni_session";

export type Role = "reader" | "admin";
export type UserStatus = "pending" | "active" | "rejected" | "suspended";

export interface SessionUser {
  id: number;
  username: string;
  name: string;
  role: Role;
  status: UserStatus;
  must_change_password: boolean;
  locked: boolean;
  created_at: string;
  reviewed_at: string | null;
  last_login_at: string | null;
}

export class AuthUnavailable extends Error {}

/** The user behind a session token, or null. Throws AuthUnavailable when the API cannot answer. */
export async function lookupSession(token: string | undefined): Promise<SessionUser | null> {
  if (!token) return null;
  const key = process.env.CONSOLE_API_KEY;
  if (!key) throw new AuthUnavailable("CONSOLE_API_KEY is not configured for the web server");
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/admin/accounts/session`, {
      method: "POST",
      headers: { "X-Console-Key": key, "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      cache: "no-store",
    });
  } catch (error) {
    throw new AuthUnavailable(String(error));
  }
  if (response.status === 401 || response.status === 422) return null;
  if (!response.ok) throw new AuthUnavailable(`session check failed: ${response.status}`);
  return (await response.json()) as SessionUser;
}

/** Where to go after login: a same-site path only, never another origin (open redirect). */
export function safeNext(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/")) return "/";
  if (value.startsWith("//") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return "/";
  if (value === "/login" || value.startsWith("/login?") || value === "/signup" || value.startsWith("/signup?")) return "/";
  return value;
}

export const LOGIN_MESSAGES = {
  invalid: "아이디 또는 비밀번호가 올바르지 않습니다.",
  pending: "승인 대기 중입니다. 관리자에게 승인을 요청하세요.",
  rejected: "가입 신청이 거절된 계정입니다. 관리자에게 문의하세요.",
  suspended: "사용이 정지된 계정입니다. 관리자에게 문의하세요.",
  throttled: "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.",
} as const;

export type LoginOutcome = keyof typeof LOGIN_MESSAGES;
