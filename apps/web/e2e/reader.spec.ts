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
    // one-minute view first (plan 13 C1): the insight cards wait for the five-minute view
    await expect(page.getByRole("heading", { name: "핵심 인사이트" })).toBeHidden();
    await page.getByRole("radio", { name: "5분" }).click();
    await expect(page.getByRole("heading", { name: "핵심 인사이트" })).toBeVisible();
    await page.getByRole("radio", { name: "심층" }).click();
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
    await page.getByRole("radio", { name: "심층" }).click();
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
    await page.getByRole("radio", { name: "심층" }).click();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeHidden();
    await page.getByRole("tab", { name: "인사이트" }).click();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("taxonomy explorer drills from fields into themes and switches schemes", async ({ page }) => {
    await page.goto("/radar?period=month");
    await page.getByRole("link", { name: "분류 탐색 →" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "분류 탐색" })).toBeVisible();
    await expect(page.getByRole("img", { name: "분류 분포 트리맵" })).toBeVisible();
    const firstField = page.getByRole("table").getByRole("link").first();
    await firstField.click();
    await expect(page).toHaveURL(/root=technology%3A/);
    await expect(page.getByText("기준", { exact: true })).toBeVisible();
    await page.getByRole("navigation", { name: "체계" }).getByRole("link", { name: "신호 유형" }).click();
    await expect(page).toHaveURL(/scheme=signal_type/);
    await expect(page.getByRole("table")).toBeVisible();
  });

  test("radar opens the current month, focuses a theme and filters by signal type", async ({ page }) => {
    await page.goto("/radar?period=month");
    await expect(page).toHaveURL(/\/radar\/month\/\d{4}-\d{2}$/);
    await expect(page.getByRole("heading", { level: 1, name: /기술 레이더/ })).toBeVisible();
    const theme = page.locator("#landscape a[href*='focus=theme']").first();
    const name = (await theme.getAttribute("aria-label"))!.replace(/ \d+건.*$/, "");
    await theme.click();
    await expect(page).toHaveURL(/focus=theme%3A/);
    await expect(page.getByRole("complementary", { name: "선택한 항목" }).getByRole("heading", { level: 2 })).toContainText(name);
    await page.getByRole("group", { name: "신호 유형 필터" }).getByRole("link", { name: "제품·기능 출시" }).click();
    await expect(page).toHaveURL(/signal=launch/);
    await expect(page.getByRole("group", { name: "신호 유형 필터" }).getByRole("link", { name: "제품·기능 출시" })).toHaveAttribute("aria-pressed", "true");
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

  test("ask page takes a question with a period and scope (plan 16 #1)", async ({ page }) => {
    await page.goto("/ask");
    await expect(page.getByRole("heading", { level: 1, name: "질문하기" })).toBeVisible();
    const submit = page.getByRole("button", { name: "질문", exact: true });
    await expect(submit).toBeDisabled();
    await page.getByLabel("질문", { exact: true }).fill("온디바이스 AI 칩 경쟁 동향은?");
    await expect(submit).toBeEnabled();
    await expect(page.getByLabel("기간")).toHaveValue("30");
    await expect(page.getByLabel("범위").locator("option")).not.toHaveCount(1);
  });

  test("patent signals switch between months and quarters (plan 16 #5)", async ({ page }) => {
    await page.goto("/patents");
    await expect(page.getByRole("heading", { level: 1, name: "특허 신호" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /월별 특허 신호/ })).toBeVisible();
    await page.getByRole("link", { name: "분기별" }).click();
    await expect(page).toHaveURL(/kind=quarter/);
    await expect(page.getByRole("heading", { name: /분기별 특허 신호/ })).toBeVisible();
  });

  test("deals page filters by kind and period (plan 16 #8)", async ({ page }) => {
    await page.goto("/deals");
    await expect(page.getByRole("heading", { level: 1, name: /투자·제휴/ })).toBeVisible();
    await page.getByLabel("유형").getByRole("link", { name: /^제휴/ }).click();
    await expect(page).toHaveURL(/kind=partnership/);
    await page.getByLabel("기간").getByRole("link", { name: "1년" }).click();
    await expect(page).toHaveURL(/days=365/);
  });
});
