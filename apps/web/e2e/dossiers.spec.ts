import { expect, test } from "@playwright/test";

// plan 16 #4: a dossier gathers cards by keyword; hypotheses are added on the page.
test.describe("dossiers", () => {
  test("creates a dossier, shows its cards and takes a hypothesis", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    const title = `온디바이스 칩 ${Date.now()}`;
    await page.goto("/dossiers/new");
    await page.getByLabel("제목").fill(title);
    await page.getByRole("textbox", { name: /^키워드/ }).fill("온디바이스");
    await page.getByRole("textbox", { name: "제외 단어" }).fill("폴더블");
    await page.getByRole("button", { name: "만들기" }).click();

    await expect(page).toHaveURL(/\/dossiers\/\d+$/);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByLabel("수집 조건").getByText("키워드: 온디바이스")).toBeVisible();
    await expect(page.getByRole("link", { name: "삼성, 차세대 온디바이스 AI 칩 공개" }).first()).toBeVisible();

    await page.getByLabel("새 가설").fill("온디바이스 AI가 플래그십 기본 사양이 된다");
    await page.getByRole("button", { name: "가설 추가" }).click();
    await expect(page.getByText("온디바이스 AI가 플래그십 기본 사양이 된다")).toBeVisible();
    await expect(page.getByText("찬성 0 · 반대 0 · 참고 0")).toBeVisible();

    await page.goto("/dossiers");
    await expect(page.getByRole("link", { name: new RegExp(title) })).toBeVisible();
  });

  test("a dossier needs at least one criterion", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/dossiers/new");
    await page.getByLabel("제목").fill("조건 없는 주제");
    await page.getByRole("button", { name: "만들기" }).click();
    await expect(page.getByText("노드·기업·키워드·문장 중 하나는 있어야 합니다.")).toBeVisible();
  });
});
