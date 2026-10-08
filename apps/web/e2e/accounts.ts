import { type Page, expect } from "@playwright/test";

// Seeded by apps/api/scripts/e2e_seed.py (seed_accounts); the password is the same there.
export const PASSWORD = "e2e-plum-orbit-4417";
export const ADMIN = { username: "e2e.admin", name: "관리자" };
export const READER = { username: "e2e.reader", name: "독자" };
export const STATE = {
  admin: "e2e/.auth/admin.json",
  reader: "e2e/.auth/reader.json",
};

export async function logIn(page: Page, username: string, password = PASSWORD, next?: string): Promise<void> {
  await page.goto(next ? `/login?next=${encodeURIComponent(next)}` : "/login");
  await page.getByLabel("아이디").fill(username);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
}

export async function signUp(page: Page, username: string, name: string, password = PASSWORD): Promise<void> {
  await page.goto("/signup");
  await page.getByLabel("아이디").fill(username);
  await page.getByLabel("이름").fill(name);
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByLabel("비밀번호 확인").fill(password);
  await page.getByRole("checkbox", { name: "동의합니다" }).check();
  await page.getByRole("button", { name: "가입 신청" }).click();
  await expect(page.getByRole("status")).toContainText("관리자에게 승인을 요청하세요");
}
