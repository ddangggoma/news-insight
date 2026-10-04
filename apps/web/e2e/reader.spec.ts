import { expect, test } from "@playwright/test";

test.describe("reader", () => {
  test("today's briefing shows three panes with tracks, personas and evidence", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1, name: /온디바이스 AI 경쟁 본격화/ })).toBeVisible();
    await expect(page.getByText("2026년 10월 5일 (월)")).toBeVisible();
    for (const track of ["뉴스·공식", "논문·특허", "오픈소스", "커뮤니티"]) {
      await expect(page.getByRole("heading", { level: 2, name: track })).toBeVisible();
    }
    await expect(page.getByRole("navigation", { name: "주제 탐색" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "근거 지도" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "로드맵 시사점" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "시장 영향도" })).toBeVisible();
    const briefing = page.getByRole("tabpanel", { name: "브리핑" });
    await expect(briefing.getByRole("link", { name: "삼성, 차세대 온디바이스 AI 칩 공개" })).toHaveAttribute("href", /etnews\.example/);
  });

  test("previous briefing and archive", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "이전 브리핑" }).click();
    await expect(page).toHaveURL(/\/briefings\/2026-10-04$/);
    const briefing = page.getByRole("tabpanel", { name: "브리핑" });
    await expect(briefing.getByRole("link", { name: "삼성, 차세대 온디바이스 AI 칩 공개 (전일)" })).toBeVisible();

    await page.goto("/archive");
    const entries = page.getByRole("listitem").filter({ hasText: "온디바이스 AI 경쟁" });
    await expect(entries).toHaveCount(2);
    await entries.first().click();
    await expect(page).toHaveURL(/\/briefings\/2026-10-05$/);
  });

  test("search finds Korean and original titles", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("searchbox", { name: "기사 검색" }).fill("폴더블");
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/search\?q=/);
    await expect(page.getByRole("heading", { name: /‘폴더블’ 검색 결과/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /애플 폴더블 아이폰 양산 돌입/ }).first()).toBeVisible();

    await page.goto("/search?q=Micro%20RGB");
    await expect(page.getByRole("link", { name: /마이크로 RGB TV/ }).first()).toBeVisible();
  });

  test("topic wiki filters by theme and links its RSS", async ({ page }) => {
    await page.goto("/topics?business=vd");
    await expect(page.getByRole("heading", { level: 1, name: /VD/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /마이크로 RGB TV/ }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /이 주제 RSS/ })).toHaveAttribute("href", "/rss.xml?business=vd");
  });

  test("RSS feeds are valid XML", async ({ request }) => {
    const daily = await request.get("/rss.xml");
    expect(daily.headers()["content-type"]).toContain("application/rss+xml");
    const body = await daily.text();
    expect(body).toContain("<rss");
    expect(body).toContain("/briefings/2026-10-05");

    const topic = await (await request.get("/rss.xml?field=mobile_edge")).text();
    expect(topic).toContain("모바일·엣지");
  });

  test("bookmarks persist locally and export as versioned JSON", async ({ page }) => {
    await page.goto("/");
    const card = page.getByRole("article").filter({ hasText: "삼성, 마이크로 RGB TV 공개" }).first();
    await card.getByRole("button", { name: "북마크" }).click();
    await expect(card.getByRole("button", { name: "북마크 해제" })).toBeVisible();

    await page.goto("/library");
    await expect(page.getByRole("link", { name: /삼성, 마이크로 RGB TV 공개/ })).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "내보내기" }).click();
    const file = await download;
    const json = JSON.parse(await (await file.createReadStream()).toArray().then((c) => Buffer.concat(c).toString()));
    expect(json.version).toBe(1);
    expect(Object.values(json.bookmarks)).toHaveLength(1);
  });

  test("mobile switches panes with tabs @mobile", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile only");
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /온디바이스 AI 경쟁/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeHidden();
    await page.getByRole("tab", { name: "인사이트" }).click();
    await expect(page.getByRole("heading", { name: "페르소나 통찰" })).toBeVisible();
    await page.getByRole("tab", { name: "탐색" }).click();
    await expect(page.getByRole("navigation", { name: "주제 탐색" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
