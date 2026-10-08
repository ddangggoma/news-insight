import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
const setSessionCookie = vi.fn();
const redirect = vi.fn((to: string) => {
  throw new Error(`redirect:${to}`);
});

vi.mock("@/lib/api", async () => {
  class ApiError extends Error {
    constructor(
      public readonly status: number,
      message: string,
    ) {
      super(message);
    }
  }
  return { ApiError, api: { post } };
});
vi.mock("@/lib/session", () => ({
  clientHeaders: async () => ({ "X-Client-IP": "203.0.113.7" }),
  setSessionCookie,
  clearSessionCookie: vi.fn(),
  sessionToken: async () => "",
  currentUser: async () => null,
}));
vi.mock("next/navigation", () => ({ redirect }));

const { ApiError } = await import("@/lib/api");
const { signup } = await import("@/app/signup/actions");
const { login } = await import("@/app/login/actions");
const { SignupForm } = await import("@/components/auth/signup-form");

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

const filled = { username: "reader.one", name: "김독자", password: "plum-orbit-4417", confirm: "plum-orbit-4417", consent: "on" };

beforeEach(() => {
  post.mockReset();
  setSessionCookie.mockReset();
  redirect.mockClear();
});

describe("signup action", () => {
  it("sends the name with the account and forwards the client address", async () => {
    post.mockResolvedValue({ status: "pending" });
    expect(await signup({}, form(filled))).toEqual({ done: true });
    expect(post).toHaveBeenCalledWith(
      "/api/admin/accounts/signup",
      { username: "reader.one", password: "plum-orbit-4417", name: "김독자" },
      { "X-Client-IP": "203.0.113.7" },
    );
  });

  it("checks the confirmation, the name and the consent before calling the API", async () => {
    const state = await signup({}, form({ ...filled, name: " ", confirm: "different-one", consent: "" }));
    expect(state.errors).toEqual({
      name: "이름을 입력하세요.",
      confirm: "비밀번호가 서로 다릅니다.",
      consent: "개인정보 수집·이용에 동의해야 가입할 수 있습니다.",
    });
    expect(post).not.toHaveBeenCalled();
  });

  it("shows the API's message next to the field it names", async () => {
    post.mockRejectedValue(new ApiError(400, JSON.stringify({ detail: { field: "username", message: "이미 쓰고 있는 아이디입니다." } })));
    const state = await signup({}, form(filled));
    expect(state.errors).toEqual({ username: "이미 쓰고 있는 아이디입니다." });
    expect(state.values).toEqual({ username: "reader.one", name: "김독자" });
  });

  it("answers bots that fill the honeypot without creating anything", async () => {
    expect(await signup({}, form({ ...filled, website: "http://spam" }))).toEqual({ done: true });
    expect(post).not.toHaveBeenCalled();
  });
});

describe("login action", () => {
  it("tells a pending account to ask the admin for approval", async () => {
    post.mockRejectedValue(new ApiError(403, JSON.stringify({ outcome: "pending" })));
    const state = await login({}, form({ username: "reader.one", password: "plum-orbit-4417" }));
    expect(state.error).toBe("승인 대기 중입니다. 관리자에게 승인을 요청하세요.");
    expect(setSessionCookie).not.toHaveBeenCalled();
  });

  it("gives one answer for unknown users and wrong passwords", async () => {
    post.mockRejectedValue(new ApiError(401, JSON.stringify({ outcome: "invalid" })));
    const state = await login({}, form({ username: "ghost", password: "whatever-pass" }));
    expect(state.error).toBe("아이디 또는 비밀번호가 올바르지 않습니다.");
  });

  it("stores the session and returns to a safe next path only", async () => {
    post.mockResolvedValue({ token: "t", expires_at: "2026-10-21T00:00:00Z", user: { must_change_password: false } });
    await expect(login({}, form({ username: "a.b.c.d", password: "x", next: "//evil.example" }))).rejects.toThrow("redirect:/");
    await expect(login({}, form({ username: "a.b.c.d", password: "x", next: "/radar" }))).rejects.toThrow("redirect:/radar");
    expect(setSessionCookie).toHaveBeenCalledWith("t", "2026-10-21T00:00:00Z");
  });

  it("sends a temporary password to the change page", async () => {
    post.mockResolvedValue({ token: "t", expires_at: "2026-10-21T00:00:00Z", user: { must_change_password: true } });
    await expect(login({}, form({ username: "a.b.c.d", password: "x", next: "/radar" }))).rejects.toThrow(
      "redirect:/change-password",
    );
  });
});

describe("SignupForm", () => {
  it("asks for the username, name, password twice and consent; the honeypot stays hidden", () => {
    render(<SignupForm />);
    for (const label of ["아이디", "이름", "비밀번호", "비밀번호 확인"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("checkbox", { name: "동의합니다" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "웹사이트" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "가입 신청" })).toBeInTheDocument();
  });
});
