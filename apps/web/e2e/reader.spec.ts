import { expect, test } from "@playwright/test";

// Fixtures: apps/api/scripts/e2e_seed.py (two published briefings: today and yesterday, KST).

test.describe("reader", () => {
  test("explore home lists stories from the seeded week", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "삼성, 차세대 온디바이스 AI 칩 공개" }).first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link", { name: "브리핑" })).toBeVisible();
  });

  test("today's briefing shows tracks, personas, evidence, roadmap and impact", async ({ page }) => {
    await page.goto("/briefings");

    await expect(page.getByRole("heading", { level: 1, name: /온디바이스 AI 경쟁 본격화/ })).toBeVisible();
    for (const track of ["뉴스·공식", "논문·특허", "오픈소스", "커뮤니티"]) {
      await expect(page.getByRole("heading", { level: 2, name: track })).toBeVisible();
    }
    for (const panel of ["페르소나 통찰", "전략 요약", "근거 지도", "로드맵 시사점", "시장 영향도", "지난 브리핑"]) {
      await expect(page.getByRole("heading", { name: panel })).toBeVisible();
    }
    await expect(page.getByText(/품질 게이트 1\/1/)).toBeVisible();
  });

  test("previous briefing navigation and article sheet", async ({ page }) => {
    await page.goto("/briefings");
    await page.getByRole("link", { name: "이전 브리핑" }).click();
    await expect(page).toHaveURL(/\/briefings\/\d{4}-\d{2}-\d{2}$/);
    const main = page.getByRole("tabpanel", { name: "브리핑" });
    await expect(main.getByRole("link", { name: "삼성, 차세대 온디바이스 AI 칩 공개 (전일)" })).toBeVisible();

    await main.getByRole("link", { name: "삼성, 차세대 온디바이스 AI 칩 공개 (전일)" }).click();
    await expect(page).toHaveURL(/\/items\/\d+$/);
    await expect(page.getByRole("link", { name: /원문/ }).first()).toHaveAttribute("href", /etnews\.example/);
  });

  test("unknown briefing dates are 404", async ({ page }) => {
    const response = await page.goto("/briefings/2001-01-01");
    expect(response?.status()).toBe(404);
  });

  test("mobile switches briefing and insights with tabs @mobile", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile only");
    await page.goto("/briefings");
    await expect(page.getByRole("heading", { level: 1, name: /온디바이스 AI 경쟁/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeHidden();
    await page.getByRole("tab", { name: "인사이트" }).click();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("radar opens the current month, focuses a theme and filters by DX business", async ({ page }) => {
    await page.goto("/radar?period=month");
    await expect(page).toHaveURL(/\/radar\/month\/\d{4}-\d{2}$/);
    await expect(page.getByRole("heading", { level: 1, name: /기술 레이더/ })).toBeVisible();
    const theme = page.locator("#landscape a[href*='focus=theme']").first();
    const name = (await theme.getAttribute("aria-label"))!.replace(/ \d+건.*$/, "");
    await theme.click();
    await expect(page).toHaveURL(/focus=theme%3A/);
    await expect(page.getByRole("complementary", { name: "선택한 항목" }).getByRole("heading", { level: 2 })).toContainText(name);
    await page.getByRole("group", { name: "DX 사업부 필터" }).getByRole("link", { name: "MX" }).click();
    await expect(page).toHaveURL(/business=mx/);
    await expect(page.getByRole("group", { name: "DX 사업부 필터" }).getByRole("link", { name: "MX" })).toHaveAttribute("aria-pressed", "true");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("radar fits a phone @mobile", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile only");
    await page.goto("/radar?period=month");
    await expect(page.getByRole("heading", { name: "카테고리 · 테마 지도" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
