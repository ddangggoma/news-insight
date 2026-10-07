"use server";

import { ApiError, api } from "@/lib/api";
import { clientHeaders } from "@/lib/session";

export type SignupField = "username" | "password" | "confirm" | "name" | "consent" | "form";

export interface SignupState {
  done?: boolean;
  errors?: Partial<Record<SignupField, string>>;
  values?: { username: string; name: string };
}

const FIELDS: readonly SignupField[] = ["username", "password", "name"];

export async function signup(_: SignupState, form: FormData): Promise<SignupState> {
  const username = String(form.get("username") ?? "").trim();
  const name = String(form.get("name") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const values = { username, name };
  // Honeypot: people never see this field, form-filling bots do. Answer as if it worked.
  if (String(form.get("website") ?? "")) return { done: true };

  const errors: SignupState["errors"] = {};
  if (!username) errors.username = "아이디를 입력하세요.";
  if (!name) errors.name = "이름을 입력하세요.";
  if (!password) errors.password = "비밀번호를 입력하세요.";
  else if (password !== String(form.get("confirm") ?? "")) errors.confirm = "비밀번호가 서로 다릅니다.";
  if (form.get("consent") !== "on") errors.consent = "개인정보 수집·이용에 동의해야 가입할 수 있습니다.";
  if (Object.keys(errors).length) return { errors, values };

  try {
    await api.post(
      "/api/admin/accounts/signup",
      { username: username.slice(0, 64), password: password.slice(0, 256), name: name.slice(0, 100) },
      await clientHeaders(),
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 429) return { errors: { form: "가입 신청이 너무 많습니다. 잠시 후 다시 시도하세요." }, values };
    if (error.status === 400) {
      const detail = (JSON.parse(error.message) as { detail: { field: string | null; message: string } }).detail;
      const field = FIELDS.find((f) => f === detail.field) ?? "form";
      return { errors: { [field]: detail.message }, values };
    }
    throw error;
  }
  return { done: true };
}
