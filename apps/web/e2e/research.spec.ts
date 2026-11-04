import { expect, test } from "@playwright/test";

// Fixtures: apps/api/scripts/e2e_seed.py (seed_domains: papers and patents over the last 12
// weeks, the daily stats rebuilt from them; 삼성전자 self, LG전자 competitor).

test.describe("연구·특허 (plan 19)", () => {
  test("연구 opens from the menu on its overview", async ({ page }) => {
    await page.goto("/patents");
    const menu = page.getByRole("navigation", { name: "주요 메뉴" });
    await menu.getByRole("link", { name: "연구" }).click();
    await expect(page).toHaveURL(/\/research$/);
    await expect(page.getByRole("heading", { level: 1, name: "연구" })).toBeVisible();
    await expect(menu.getByRole("link", { name: "연구" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: "연구 보기" }).getByRole("link", { name: "개요" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByText("이번 기간 논문")).toBeVisible();
    await expect(page.getByText("인사이트는 매일 05시 브리핑 뒤에 작성됩니다.")).toBeVisible();
    await expect(page.getByRole("table").getByRole("rowheader", { name: "AI 모델·에이전트" })).toBeVisible();

    await page.getByRole("navigation", { name: "연구 보기" }).getByRole("link", { name: "기업·기관별" }).click();
    await expect(page).toHaveURL(/tab=companies/);
    await expect(page.getByRole("table", { name: "기업 순위" }).getByRole("link", { name: "삼성전자" })).toBeVisible();
    await page.getByRole("navigation", { name: "기관 구분" }).getByRole("link", { name: "대학·연구기관" }).click();
    await expect(page).toHaveURL(/kind=org/);
    await expect(page.getByRole("table", { name: "대학·연구기관 순위" }).getByRole("link", { name: "KAIST" })).toBeVisible();
  });

  test("특허 switches to 기업·기관별 and 추이", async ({ page }) => {
    await page.goto("/patents");
    await expect(page.getByRole("heading", { level: 1, name: "특허" })).toBeVisible();
    await expect(page.getByRole("note", { name: "데이터 범위" })).toContainText("지식재산 뉴스·EPO 공보 파일럿 기준");
    const tabs = page.getByRole("navigation", { name: "특허 보기" });

    await tabs.getByRole("link", { name: "기업·기관별" }).click();
    await expect(page).toHaveURL(/tab=companies/);
    const ranking = page.getByRole("table", { name: "출원 기업 순위" });
    await expect(ranking.getByRole("link", { name: "LG전자" })).toBeVisible();
    await ranking.getByRole("link", { name: "LG전자" }).click();
    await expect(page).toHaveURL(/company=lg-electronics/);
    await expect(page.getByRole("heading", { level: 2, name: "LG전자", exact: true })).toBeVisible();

    await tabs.getByRole("link", { name: "추이" }).click();
    await expect(page).toHaveURL(/tab=trends/);
    await expect(page).not.toHaveURL(/company=/);
    await expect(page.getByRole("heading", { name: "기술분야별 추이" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "공개국별 추이" })).toBeVisible();
    await page.getByRole("navigation", { name: "보기 방식" }).getByRole("link", { name: "표" }).click();
    await expect(page).toHaveURL(/view=table/);
    await expect(page.getByRole("table", { name: "공개국별 추이 기간별 문헌 수" })).toBeVisible();

    await page.getByRole("navigation", { name: "기간" }).getByRole("link", { name: "분기" }).click();
    await expect(page).toHaveURL(/period=quarter/);
    await expect(tabs.getByRole("link", { name: "추이" })).toHaveAttribute("aria-current", "page");
  });

  test("연구 fits a phone @mobile", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile only");
    await page.goto("/research");
    await expect(page.getByRole("navigation", { name: "하단 메뉴" }).getByRole("link", { name: "연구" })).toHaveAttribute("aria-current", "page");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
