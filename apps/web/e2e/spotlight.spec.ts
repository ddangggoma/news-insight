import { expect, test } from "@playwright/test";

// Fixtures: apps/api/scripts/e2e_seed.py (a published spotlight for today and yesterday, KST).
// Today: news has three 최근 24시간 entries (one moved by Opus with a note, one fallback) and
// one 지속 주목 entry, product has one with a product name, ai and oss have one each; interview,
// community, research and patent are empty. Entries carry their lead card's field; two have
// insight tags and signals.
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
    await expect(page.getByRole("region", { name: /최근 24시간/ }).getByLabel("새로 진입")).toHaveText("NEW");
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

  test("the news tab splits 최근 24시간 from 지속 주목, with tags, and the field filter narrows it", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight?tab=news");
    const main = page.getByRole("main");
    await expect(main.getByRole("heading", { level: 2, name: /최근 24시간/ })).toContainText("3건");
    const lasting = main.getByRole("region", { name: /지속 주목/ });
    await expect(lasting.getByRole("heading", { level: 2 })).toContainText("1건");
    await expect(lasting.getByRole("link", { name: "마이크로 RGB 패널 경쟁이 일주일째 이어졌다" })).toBeVisible();
    await expect(lasting.getByText("장기 화제")).toBeVisible();
    await expect(lasting.getByText("7일 중 5일")).toBeVisible();
    await expect(main.getByText("NPU 2배")).toBeVisible();

    const fields = page.getByRole("group", { name: "분야 필터" });
    await fields.getByRole("button", { name: /무선·네트워크/ }).click();
    await expect(fields.getByRole("button", { name: /무선·네트워크/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page).toHaveURL(/field=connectivity/);
    await expect(main.getByRole("link", { name: "스마트홈 표준 갱신 소식" })).toBeVisible();
    await expect(main.getByRole("link", { name: "온디바이스 칩 소식이 가장 크게 번졌다" })).toHaveCount(0);
    await expect(main.getByRole("link", { name: "마이크로 RGB 패널 경쟁이 일주일째 이어졌다" })).toHaveCount(0);

    // the address keeps the filter: a reload opens the same narrowed list
    await page.reload();
    await expect(page.getByRole("group", { name: "분야 필터" }).getByRole("button", { name: /무선·네트워크/ })).toHaveAttribute("aria-pressed", "true");
    await expect(main.getByRole("link", { name: "온디바이스 칩 소식이 가장 크게 번졌다" })).toHaveCount(0);

    await page.getByRole("group", { name: "묶음 필터" }).getByRole("button", { name: "지속 주목" }).click();
    await expect(page).toHaveURL(/group=sustained/);
    await expect(main.getByText("조건에 맞는 항목이 없습니다")).toBeVisible();
  });

  test("AI 모델·서비스 holds the benchmarks below its ranked list; the AI 모델 tab is gone", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight");
    const tabs = page.getByRole("navigation", { name: "주목 받는 보기" });
    await expect(tabs.getByRole("link", { name: "AI 모델", exact: true })).toHaveCount(0);
    await tabs.getByRole("link", { name: "AI 모델·서비스", exact: true }).click();
    await expect(page).toHaveURL(/tab=ai/);
    await expect(page.getByRole("link", { name: "스마트폰용 4비트 LLM이 주목받았다" })).toBeVisible();

    // the benchmarks follow the ranked list, collected from the sites' responses of 2026-11-04
    const bench = page.getByRole("region", { name: "AI 모델 벤치마크" });
    await expect(bench).toBeVisible();
    const deepswe = bench.getByRole("region", { name: "DeepSWE" });
    const dsTable = deepswe.getByRole("table", { name: "DeepSWE 순위표" });
    // the site's default table: 21 models, gpt-5.6-terra (hidden on the site) not among them
    await expect(dsTable.getByRole("rowheader").first()).toContainText("gpt-6-astra");
    await expect(dsTable.getByRole("rowheader")).toHaveCount(20);
    await expect(dsTable.getByText("gpt-5.6-terra")).toHaveCount(0);
    await expect(deepswe.getByRole("button", { name: "모델 고르기" })).toContainText("(21/28)");
    await expect(deepswe.getByText("2026년 9월 22일", { exact: false })).toBeVisible();

    const arena = bench.getByRole("region", { name: "LMArena" });
    const arenaTable = arena.getByRole("table", { name: /LMArena 텍스트 순위표/ });
    // rank 9 is the effort-less "Claude Opus 4.6", its own row as on arena.ai
    await expect(arenaTable.getByRole("rowheader").nth(8)).toHaveText(/^9.*Claude Opus 4\.6$/);
    await expect(arena.getByText("Style Control (사이트 기본값)")).toBeVisible();
    await arena.getByRole("tab", { name: "검색" }).click();
    await expect(arena.getByRole("table", { name: /LMArena 검색 순위표/ }).getByRole("rowheader").nth(1)).toContainText("qwen3.8-max");
    await expect(arena.getByText("None (사이트 기본값)")).toBeVisible();

    const livebench = bench.getByRole("region", { name: "LiveBench" });
    await expect(livebench.getByRole("table").getByRole("rowheader").first()).toContainText("Claude Fable 5.1");
    await expect(bench.getByRole("region", { name: "Artificial Analysis" }).getByText("키 미설정")).toBeVisible();
  });

  test("the agent benchmarks lead: Terminal-Bench, OSWorld 2.0 and τ²-bench, then Epoch AI among the models", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight?tab=ai#benchmarks");
    const bench = page.getByRole("region", { name: "AI 모델 벤치마크" });
    // collected from the sites' responses of 2026-11-08 (trimmed fixtures)
    const agents = bench.getByRole("group", { name: "AI 에이전트 벤치마크" });
    await expect(agents.getByRole("heading", { level: 4 })).toHaveText([/^Terminal-Bench/, /^OSWorld 2\.0/, /^τ²-bench/]);
    const tb = agents.getByRole("region", { name: "Terminal-Bench" });
    const tbTable = tb.getByRole("table", { name: "Terminal-Bench 4.0 순위표" });
    // tbench.ai's best-effort table: GPT-6 Astra and GPT-6.1 Sol share third place
    await expect(tbTable.getByRole("rowheader")).toHaveCount(6);
    await expect(tbTable.getByRole("rowheader").nth(3)).toHaveText(/^3/);
    await expect(tbTable.getByRole("row").nth(4)).toContainText("Codex");
    await expect(tbTable.getByText("64.8% ± 3.1%")).toBeVisible();
    await expect(tb.getByRole("list", { name: "에이전트별 최고 점수" }).getByRole("listitem")).toHaveCount(2);
    await tb.getByRole("group", { name: "에이전트별" }).getByRole("button", { name: "Codex" }).click();
    await expect(tbTable.getByRole("rowheader")).toHaveCount(2);
    await tb.getByRole("button", { name: "TB 2.1" }).click();
    await expect(tb.getByRole("table", { name: "Terminal-Bench 2.1 순위표" }).getByRole("row").nth(1)).toContainText("Codex");

    const os = agents.getByRole("region", { name: "OSWorld 2.0" });
    await expect(os.getByRole("table", { name: "OSWorld 2.0 순위표" }).getByRole("rowheader").first()).toContainText("Claude Opus 5");
    await expect(os.getByText("44.33%")).toBeVisible();

    const tau = agents.getByRole("region", { name: "τ²-bench" });
    // the card opens on τ³-Banking, the leaderboard's first tab
    await expect(tau.getByRole("table").getByRole("rowheader").first()).toContainText("Claude Opus 5");
    await tau.getByRole("button", { name: "τ²-bench" }).click();
    await expect(tau.getByRole("table").getByRole("rowheader").first()).toContainText("Claude Opus 4.5");

    const models = bench.getByRole("group", { name: "AI 모델 벤치마크" });
    const epoch = models.getByRole("region", { name: "Epoch AI" });
    await expect(epoch.getByText("ECI 상위 6개 모델")).toBeVisible();
    await expect(epoch.getByRole("table").getByRole("rowheader").first()).toContainText("GPT-6 Astra");
    await expect(epoch.getByText("CC BY 4.0")).toBeVisible();
    await epoch.getByRole("button", { name: "GPQA Diamond" }).click();
    await expect(epoch.getByRole("table").getByText("96.4%")).toBeVisible();
  });

  test("an old AI 모델 link lands on the benchmarks under AI 모델·서비스", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight?tab=models");
    await expect(page).toHaveURL(/\/spotlight\?tab=ai#benchmarks$/);
    const tabs = page.getByRole("navigation", { name: "주목 받는 보기" });
    await expect(tabs.getByRole("link", { name: "AI 모델·서비스", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 2, name: "AI 모델 벤치마크" })).toBeInViewport();
  });

  test("@mobile the benchmarks read on a phone", async ({ page }) => {
    await page.goto("/spotlight?tab=ai#benchmarks");
    const bench = page.getByRole("region", { name: "AI 모델 벤치마크" });
    const table = bench.getByRole("table", { name: "DeepSWE 순위표" });
    await expect(table.getByRole("rowheader").first()).toContainText("gpt-6-astra");
    // body text at least 14 px
    const size = await table.getByRole("rowheader").first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(size).toBeGreaterThanOrEqual(14);
    const tb = bench.getByRole("table", { name: "Terminal-Bench 4.0 순위표" });
    await expect(tb.getByRole("row").nth(1)).toContainText("Claude Code");
    const tbSize = await tb.getByRole("rowheader").first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(tbSize).toBeGreaterThanOrEqual(14);
    // the page does not scroll sideways: wide tables scroll inside their own box
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
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
