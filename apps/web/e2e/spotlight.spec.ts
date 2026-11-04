import { expect, test } from "@playwright/test";

// Fixtures: apps/api/scripts/e2e_seed.py (a published spotlight for today and yesterday, KST).
// Today: news has three entries (one moved by Opus with a note, one fallback), product has one
// with a product name, ai and oss have one each; interview, community, research and patent are
// empty.
test.describe("spotlight", () => {
  test("opens from the menu with the day's headline and every section", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/");
    await page.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link", { name: "주목 받는" }).click();
    await expect(page).toHaveURL(/\/spotlight$/);
    await expect(page.getByRole("heading", { level: 1, name: "주목 받는" })).toBeVisible();
    await expect(page.getByText("오늘은 온디바이스 AI 칩과 폴더블 소식이 화제를 주도했다")).toBeVisible();
    // the four sections without a hot item say so
    await expect(page.getByText("오늘은 기준을 넘는 화제가 없습니다")).toHaveCount(4);
    // the overview keeps the address date-free so the page rolls forward with the days
    const newsBlock = page.getByRole("main").locator("section", { has: page.getByRole("heading", { level: 2, name: "뉴스" }) });
    await expect(newsBlock.getByRole("link", { name: "뉴스", exact: true })).toHaveAttribute("href", "/spotlight?tab=news");
  });

  test("the news tab shows Opus's ranking, change badges and the fallback mark", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight");
    await page.getByRole("navigation", { name: "주목 받는 보기" }).getByRole("link", { name: "뉴스" }).click();
    await expect(page).toHaveURL(/tab=news/);

    const rows = page.getByRole("listitem").filter({ hasText: /온디바이스 칩 소식이|폴더블 양산 소식이|스마트홈 표준/ });
    await expect(rows).toHaveCount(3);
    await expect(page.getByText("통계 2위")).toBeVisible();
    await expect(page.getByText("파급력이 커서 통계보다 올림")).toBeVisible();
    await expect(page.getByText("Opus 미작성")).toHaveCount(1);
    // against yesterday's list
    await expect(page.getByLabel("1계단 상승")).toHaveText("▲1");
    await expect(page.getByLabel("1계단 하락")).toHaveText("▼1");
    await expect(page.getByLabel("새로 진입")).toHaveText("NEW");
    // the lead item's link resolves from the item ids
    await expect(page.getByRole("link", { name: "온디바이스 칩 소식이 가장 크게 번졌다" })).toHaveAttribute("href", /^https:\/\/etnews\.example\//);
  });

  test("a product carries its name; a section without a hot item is explained", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight?tab=product");
    await expect(page.getByRole("link", { name: "마이크로 RGB TV 공개" })).toBeVisible();
    await expect(page.getByText("Micro RGB TV", { exact: true })).toBeVisible();

    await page.goto("/spotlight?tab=patent");
    await expect(page.getByText("오늘은 기준을 넘는 화제가 없습니다")).toBeVisible();
  });

  test("AI 모델·서비스 has its own tab beside the leaderboards", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight");
    const tabs = page.getByRole("navigation", { name: "주목 받는 보기" });
    await expect(tabs.getByRole("link", { name: "AI 모델", exact: true })).toHaveAttribute("href", "/spotlight?tab=models");
    await tabs.getByRole("link", { name: "AI 모델·서비스", exact: true }).click();
    await expect(page).toHaveURL(/tab=ai/);
    await expect(page.getByRole("link", { name: "스마트폰용 4비트 LLM이 주목받았다" })).toBeVisible();
  });

  test("an earlier day opens by date; an impossible or unpublished date shows the not-found page", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight");
    const earlier = await page.getByRole("combobox", { name: "날짜" }).locator("option").nth(1).getAttribute("value");
    expect(earlier).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    await page.goto(`/spotlight?date=${earlier}`);
    await expect(page.getByText("전일에는 폴더블 양산 소식이 화제였다")).toBeVisible();

    for (const date of ["2026-13-45", "2020-01-01"]) {
      // loading.tsx streams the page, so the status is already 200: the not-found page is the proof
      await page.goto(`/spotlight?date=${date}`);
      await expect(page.getByText("This page could not be found.")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: "주목 받는" })).toHaveCount(0);
    }
  });
});
