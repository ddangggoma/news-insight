import { type Browser, type Page, expect, test } from "@playwright/test";

import { ADMIN, PASSWORD, READER, STATE, logIn, signUp } from "./accounts";

const unique = (prefix: string) => `${prefix}.${Date.now().toString(36)}`;

async function asAdmin(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: STATE.admin });
  return context.newPage();
}

async function approve(browser: Browser, username: string): Promise<Page> {
  const admin = await asAdmin(browser);
  await admin.goto("/console/users");
  const row = admin.getByRole("row").filter({ hasText: username });
  await row.getByRole("button", { name: "승인" }).click();
  await expect(admin.getByText(/님을 승인했습니다/)).toBeVisible();
  return admin;
}

test.describe("without a session", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("every page goes to the login page and comes back after login", async ({ page }) => {
    await page.goto("/briefings");
    await expect(page).toHaveURL(/\/login\?next=%2Fbriefings$/);
    await expect(page.getByRole("heading", { name: "DX 인텔리전스 로그인" })).toBeVisible();

    await page.getByLabel("아이디").fill(READER.username);
    await page.getByLabel("비밀번호").fill(PASSWORD);
    await page.getByRole("button", { name: "로그인" }).click();
    await expect(page).toHaveURL(/\/briefings$/);
  });

  test("the console and data routes are closed too", async ({ page, request }) => {
    await page.goto("/console");
    await expect(page).toHaveURL(/\/login\?next=%2Fconsole$/);
    const topic = await request.get("/radar/week/2026-W40/topic?kind=field&value=ai", { maxRedirects: 0 });
    expect(topic.status()).toBe(307);
    expect(topic.headers().location).toMatch(/\/login\?next=/);
  });

  test("a forged session cookie is rejected", async ({ page, context }) => {
    await context.addCookies([{ name: "ni_session", value: "forged", url: "http://127.0.0.1:8713" }]);
    await page.goto("/radar");
    await expect(page).toHaveURL(/\/login\?next=%2Fradar$/);
  });

  test("a wrong password and an unknown user get the same answer", async ({ page }) => {
    await logIn(page, READER.username, "not-the-password");
    await expect(page.getByRole("main").getByRole("alert")).toHaveText("아이디 또는 비밀번호가 올바르지 않습니다.");
    await logIn(page, "nobody.here", "not-the-password");
    await expect(page.getByRole("main").getByRole("alert")).toHaveText("아이디 또는 비밀번호가 올바르지 않습니다.");
  });

  test("sign-up waits for approval, then the admin approves it", async ({ page, browser }) => {
    const username = unique("newbie");
    await signUp(page, username, "새 독자");

    await logIn(page, username);
    await expect(page.getByRole("main").getByRole("alert")).toHaveText("승인 대기 중입니다. 관리자에게 승인을 요청하세요.");
    await expect(page).toHaveURL(/\/login$/);

    const admin = await approve(browser, username);
    await admin.close();

    await logIn(page, username);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: "계정 메뉴: 새 독자" })).toBeVisible();
  });

  test("sign-up checks the form before sending it", async ({ page }) => {
    await page.goto("/signup");
    await page.getByLabel("아이디").fill(READER.username);
    await page.getByLabel("이름").fill("중복");
    await page.getByLabel("비밀번호", { exact: true }).fill(PASSWORD);
    await page.getByLabel("비밀번호 확인").fill(PASSWORD);
    await page.getByRole("button", { name: "가입 신청" }).click();
    await expect(page.getByText("개인정보 수집·이용에 동의해야 가입할 수 있습니다.")).toBeVisible();

    await page.getByLabel("비밀번호", { exact: true }).fill(PASSWORD);
    await page.getByLabel("비밀번호 확인").fill(PASSWORD);
    await page.getByRole("checkbox", { name: "동의합니다" }).check();
    await page.getByRole("button", { name: "가입 신청" }).click();
    await expect(page.getByText("이미 쓰고 있는 아이디입니다.")).toBeVisible();
  });

  test("a reset password works once, then must be replaced", async ({ page, browser }) => {
    const username = unique("reset");
    await signUp(page, username, "초기화 대상");
    const admin = await approve(browser, username);

    admin.on("dialog", (dialog) => dialog.accept());
    await admin.goto("/console/users?status=active");
    await admin.getByRole("row").filter({ hasText: username }).getByRole("button", { name: "비밀번호 초기화" }).click();
    const temporary = (await admin.getByTestId("temporary-password").textContent())?.trim() ?? "";
    expect(temporary.length).toBeGreaterThanOrEqual(16);
    await admin.close();

    await logIn(page, username, temporary);
    await expect(page).toHaveURL(/\/change-password$/);
    await page.goto("/radar");
    await expect(page).toHaveURL(/\/change-password$/);

    await page.getByLabel("임시 비밀번호").fill(temporary);
    await page.getByLabel("새 비밀번호", { exact: true }).fill("fresh-harbor-7731");
    await page.getByLabel("새 비밀번호 확인").fill("fresh-harbor-7731");
    await page.getByRole("button", { name: "비밀번호 변경" }).click();
    await expect(page).toHaveURL(/\/account\?changed=1$/);
    await expect(page.getByRole("status")).toContainText("비밀번호를 바꿨습니다");
  });

  test("logout ends the session", async ({ page }) => {
    await logIn(page, READER.username);
    await expect(page).toHaveURL(/\/$/);
    await page.getByRole("button", { name: `계정 메뉴: ${READER.name}` }).click();
    await page.getByRole("menuitem", { name: "로그아웃" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("as a reader", () => {
  test.use({ storageState: STATE.reader });

  test("the console stays closed", async ({ page }) => {
    await page.goto("/console/users");
    await expect(page).toHaveURL(/127\.0\.0\.1:8713\/$/);
    await page.getByRole("button", { name: `계정 메뉴: ${READER.name}` }).click();
    await expect(page.getByRole("menuitem", { name: "운영 콘솔" })).toHaveCount(0);
  });
});

test.describe("as the admin", () => {
  test.use({ storageState: STATE.admin });

  test("the console shows the user list and an account's audit trail", async ({ page }) => {
    await page.goto("/console/users?status=active");
    await expect(page.getByRole("heading", { level: 1, name: "사용자" })).toBeVisible();
    await expect(page.getByRole("row").filter({ hasText: ADMIN.username })).toContainText("내 계정");
    await page.getByRole("link", { name: READER.username }).click();
    await expect(page.getByRole("heading", { level: 1, name: `${READER.name} (${READER.username})` })).toBeVisible();
    await expect(page.getByRole("cell", { name: "승인", exact: true })).toBeVisible();
  });
});
