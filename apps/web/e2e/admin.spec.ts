import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { E2E_ENV } from "../playwright.config";

function loginLink(): string {
  const output = execFileSync("uv", ["run", "news-insight", "admin", "link"], {
    cwd: path.resolve(import.meta.dirname, "../../api"),
    env: { ...process.env, ...E2E_ENV },
    encoding: "utf-8",
  });
  return output.trim().split("\n").at(-1) ?? "";
}

test.describe("admin login guard", () => {
  test("console redirects to login without a session", async ({ page }) => {
    await page.goto("/console");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "운영 콘솔 로그인" })).toBeVisible();
  });

  test("a forged session cookie is rejected", async ({ page, context }) => {
    await context.addCookies([{ name: "ni_admin", value: "forged", url: "http://127.0.0.1:8713" }]);
    await page.goto("/console/sources");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("login request never reveals the admin address", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("관리자 이메일").fill("someone@example.com");
    await page.getByRole("button", { name: "로그인 링크 받기" }).click();
    await expect(page.getByRole("status")).toContainText("관리자 주소라면 로그인 링크를 보냈습니다");
  });

  test("magic link logs in once, then logout ends the session", async ({ page }) => {
    const link = loginLink();
    expect(link).toMatch(/\/login\/verify\?token=/);

    await page.goto(link);
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page).toHaveURL(/\/console$/);
    await expect(page.getByText("ddangggoma@gmail.com")).toBeVisible();

    await page.getByRole("button", { name: "로그아웃" }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.goto("/console");
    await expect(page).toHaveURL(/\/login$/);

    await page.goto(link);
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page).toHaveURL(/\/login\?error=expired$/);
  });
});
