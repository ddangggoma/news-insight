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

    // the ranked list (오늘의 구도 above it repeats some of these titles)
    const now = page.getByRole("region", { name: /최근 24시간/ });
    const rows = now.getByRole("listitem").filter({ hasText: /온디바이스 칩 소식이|폴더블 양산 소식이|스마트홈 표준/ });
    await expect(rows).toHaveCount(3);
    await expect(page.getByText("통계 2위")).toBeVisible();
    await expect(page.getByText("파급력이 커서 통계보다 올림")).toBeVisible();
    await expect(page.getByText("Opus 미작성")).toHaveCount(1);
    // against yesterday's list
    await expect(page.getByLabel("1계단 상승")).toHaveText("▲1");
    await expect(page.getByLabel("1계단 하락")).toHaveText("▼1");
    await expect(page.getByRole("region", { name: /최근 24시간/ }).getByLabel("새로 진입")).toHaveText("NEW");
    // the lead item's link resolves from the item ids
    await expect(now.getByRole("link", { name: "온디바이스 칩 소식이 가장 크게 번졌다" })).toHaveAttribute("href", /^https:\/\/etnews\.example\//);
  });

  test("the news tab opens with 오늘의 구도, the interest areas and each entry's 시사점", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight?tab=news");
    const themes = page.getByRole("region", { name: /오늘의 구도/ });
    await expect(themes.getByRole("heading", { name: /온디바이스 AI 칩 경쟁/ })).toBeVisible();
    await expect(themes.getByRole("heading", { name: /폼팩터와 패널 전환/ })).toBeVisible();
    const areas = page.getByRole("region", { name: /관심 분야별 정리/ });
    await expect(areas.getByRole("heading", { name: "모바일·온디바이스 AI" })).toBeVisible();
    await expect(areas.getByRole("heading", { name: "디스플레이" })).toBeVisible();
    await expect(page.getByText("폴더블 양산 확대는 패널 단가와 힌지 공급망 협상력에 영향을 준다.")).toBeVisible();
    // a title in the overview jumps to its row in the list
    await themes.getByRole("link", { name: "온디바이스 칩 소식이 가장 크게 번졌다" }).click();
    await expect(page).toHaveURL(/#entry-n-chip$/);
    // a day published before the overview has none
    const yesterday = new Date(Date.now() + 9 * 3600_000 - 24 * 3600_000).toISOString().slice(0, 10); // KST
    await page.goto(`/spotlight?tab=news&date=${yesterday}`);
    await expect(page.getByRole("region", { name: /최근 24시간/ })).toBeVisible();
    await expect(page.getByRole("region", { name: /오늘의 구도/ })).toHaveCount(0);
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

  test("벤치마크 is a tab of its own, one site at a time; AI 모델·서비스 keeps only its ranked list", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    await page.goto("/spotlight");
    const tabs = page.getByRole("navigation", { name: "주목 받는 보기" });
    await expect(tabs.getByRole("link", { name: "AI 모델", exact: true })).toHaveCount(0);
    await tabs.getByRole("link", { name: "AI 모델·서비스", exact: true }).click();
    await expect(page).toHaveURL(/tab=ai/);
    await expect(page.getByRole("link", { name: "스마트폰용 4비트 LLM이 주목받았다" })).toBeVisible();
    await expect(page.getByRole("region", { name: "AI 벤치마크" })).toHaveCount(0);

    await tabs.getByRole("link", { name: "벤치마크", exact: true }).click();
    await expect(page).toHaveURL(/tab=benchmarks/);
    const bench = page.getByRole("region", { name: "AI 벤치마크" });
    await expect(bench).toBeVisible();
    const menu = bench.getByRole("navigation", { name: "벤치마크 사이트" });
    // the menu's first site opens; no other site's card is in the page
    await expect(menu.getByRole("link", { name: "Terminal-Bench" })).toHaveAttribute("aria-current", "page");
    await expect(bench.getByRole("region", { name: "Terminal-Bench" })).toBeVisible();
    await expect(bench.getByRole("region", { name: "LMArena" })).toHaveCount(0);
    await expect(menu.getByRole("group", { name: "AI 에이전트" }).getByRole("link")).toHaveText([/^Terminal-Bench/, /^OSWorld 2\.0/, /^τ²-bench/, /^Vals Index/, /^Vending-Bench 2/]);
    await expect(menu.getByRole("group", { name: "AI 모델" }).getByRole("link")).toHaveText([/^LiveBench/, /^LMArena/, /^Epoch AI/, /^Scale SEAL/, /^SimpleBench/, /^ForecastBench/]);
    // DeepSWE and Artificial Analysis left the page on 2026-11-13
    await expect(bench.getByText(/DeepSWE|Artificial Analysis/)).toHaveCount(0);

    // collected from the sites' responses of 2026-11-04
    await menu.getByRole("link", { name: "LMArena" }).click();
    await expect(page).toHaveURL(/tab=benchmarks&site=lmarena/);
    const arena = bench.getByRole("region", { name: "LMArena" });
    const arenaTable = arena.getByRole("table", { name: /LMArena 텍스트 순위표/ });
    // rank 9 is the effort-less "Claude Opus 4.6", its own row as on arena.ai
    await expect(arenaTable.getByRole("rowheader").nth(8)).toHaveText(/^9.*Claude Opus 4\.6$/);
    await expect(arena.getByText("Style Control (사이트 기본값)")).toBeVisible();
    await arena.getByRole("tab", { name: "검색" }).click();
    await expect(arena.getByRole("table", { name: /LMArena 검색 순위표/ }).getByRole("rowheader").nth(1)).toContainText("qwen3.8-max");
    await expect(arena.getByText("None (사이트 기본값)")).toBeVisible();
    await expect(bench.getByRole("region", { name: "Terminal-Bench" })).toHaveCount(0);

    await menu.getByRole("link", { name: "LiveBench" }).click();
    await expect(page).toHaveURL(/site=livebench/);
    const livebench = bench.getByRole("region", { name: "LiveBench" });
    await expect(livebench.getByRole("table").getByRole("rowheader").first()).toContainText("Claude Fable 5.1");
  });

  test("the agent benchmarks: Terminal-Bench, OSWorld 2.0 and τ²-bench, and Epoch AI among the models", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    // collected from the sites' responses of 2026-11-08 (trimmed fixtures)
    await page.goto("/spotlight?tab=benchmarks");
    const bench = page.getByRole("region", { name: "AI 벤치마크" });
    const tb = bench.getByRole("region", { name: "Terminal-Bench" });
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

    await page.goto("/spotlight?tab=benchmarks&site=osworld");
    const os = bench.getByRole("region", { name: "OSWorld 2.0" });
    await expect(os.getByRole("table", { name: "OSWorld 2.0 순위표" }).getByRole("rowheader").first()).toContainText("Claude Opus 5");
    await expect(os.getByText("44.33%")).toBeVisible();

    await page.goto("/spotlight?tab=benchmarks&site=tau2");
    const tau = bench.getByRole("region", { name: "τ²-bench" });
    // the card opens on τ³-Banking, the leaderboard's first tab
    await expect(tau.getByRole("table").getByRole("rowheader").first()).toContainText("Claude Opus 5");
    await tau.getByRole("button", { name: "τ²-bench" }).click();
    await expect(tau.getByRole("table").getByRole("rowheader").first()).toContainText("Claude Opus 4.5");

    await page.goto("/spotlight?tab=benchmarks&site=epoch");
    const epoch = bench.getByRole("region", { name: "Epoch AI" });
    await expect(epoch.getByText("ECI 상위 6개 모델")).toBeVisible();
    await expect(epoch.getByRole("table").getByRole("rowheader").first()).toContainText("GPT-6 Astra");
    await expect(epoch.getByText("라이선스: CC BY 4.0")).toBeVisible();
    await epoch.getByRole("button", { name: "GPQA Diamond" }).click();
    await expect(epoch.getByRole("table").getByText("96.4%")).toBeVisible();
  });

  test("the sites added 2026-11-13 open as their own default views", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    // collected from the sites' responses of 2026-11-13 (trimmed fixtures)
    const bench = page.getByRole("region", { name: "AI 벤치마크" });

    await page.goto("/spotlight?tab=benchmarks&site=seal");
    const seal = bench.getByRole("region", { name: "Scale SEAL" });
    const hle = seal.getByRole("table", { name: "Scale SEAL Humanity's Last Exam (Diamond) 순위표" });
    await expect(hle.getByRole("row").nth(1)).toContainText("claude-fable-5-2");
    await expect(hle.getByRole("row").nth(1)).toContainText("72.40 ± 2.68");
    // the page's open tab (HARD) comes before Full
    await expect(seal.getByRole("group", { name: "SEAL 벤치마크" }).getByRole("button")).toHaveText(["Humanity's Last Exam (Diamond)", "MCP Atlas", "SWE-Bench Pro V2 HARD", "SWE-Bench Pro V2 Full"]);
    await seal.getByRole("button", { name: "SWE-Bench Pro V2 Full" }).click();
    const swe = seal.getByRole("table", { name: "Scale SEAL SWE-Bench Pro V2 Full 순위표" });
    // Rank (UB) is shared: two entries at rank 2
    await expect(swe.getByRole("rowheader").nth(1)).toHaveText(/^2/);
    await expect(swe.getByRole("rowheader").nth(2)).toHaveText(/^2/);

    await page.goto("/spotlight?tab=benchmarks&site=vals");
    const vals = bench.getByRole("region", { name: "Vals Index" });
    const valsRow = vals.getByRole("table", { name: "Vals Index 순위표" }).getByRole("row").nth(1);
    for (const text of ["Claude Fable 5.2", "71.31%", "$17.94", "31.31m", "43m42s"]) await expect(valsRow).toContainText(text);
    await expect(vals.getByRole("button", { name: "개발사별 최고 모델" })).toHaveAttribute("aria-pressed", "true");
    await expect(vals.getByText("라이선스: CC BY 4.0")).toBeVisible();

    await page.goto("/spotlight?tab=benchmarks&site=vending_bench");
    const vending = bench.getByRole("region", { name: "Vending-Bench 2" });
    const vendingTable = vending.getByRole("table", { name: "Vending-Bench 2 순위표" });
    await expect(vendingTable.getByRole("row").nth(1)).toContainText("Gemini 4 Carbon");
    await expect(vendingTable.getByRole("row").nth(1)).toContainText("$16,484.21");
    await expect(vendingTable.getByRole("rowheader")).toHaveCount(10);
    await vending.getByRole("button", { name: "더 보기" }).click();
    await expect(vendingTable.getByRole("rowheader")).toHaveCount(12);
    await expect(vending.getByText(/출처: .*Andon Labs.*Epoch AI/)).toBeVisible();

    await page.goto("/spotlight?tab=benchmarks&site=simplebench");
    const simple = bench.getByRole("region", { name: "SimpleBench" }).getByRole("table", { name: "SimpleBench 순위표" });
    await expect(simple.getByRole("row").nth(1)).toContainText("Highest Human Score*");
    await expect(simple.getByRole("row").nth(2)).toContainText("1st");
    await expect(simple.getByRole("row").nth(2)).toContainText("Claude Fable 5.2");
    await expect(simple.getByRole("row").nth(2)).toContainText("94.9%");

    await page.goto("/spotlight?tab=benchmarks&site=forecastbench");
    const forecast = bench.getByRole("region", { name: "ForecastBench" });
    const forecastTable = forecast.getByRole("table", { name: "ForecastBench 토너먼트 순위표" });
    // anonymous teams are hidden as on the site, so the first row is the file's rank 3
    await expect(forecastTable.getByRole("row").nth(1)).toContainText("fire hedgehog");
    await expect(forecastTable.getByRole("rowheader").first()).toHaveText(/^3/);
    await forecast.getByRole("checkbox", { name: /익명 팀 보기/ }).check();
    await expect(forecastTable.getByRole("row").nth(1)).toContainText("model-4");
  });

  test("old links to the leaderboards land on the 벤치마크 tab", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop flow");
    const tabs = page.getByRole("navigation", { name: "주목 받는 보기" });
    // the former AI 모델 tab: a server redirect
    await page.goto("/spotlight?tab=models");
    await expect(page).toHaveURL(/\/spotlight\?tab=benchmarks$/);
    await expect(tabs.getByRole("link", { name: "벤치마크", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 2, name: "AI 벤치마크" })).toBeVisible();
    // from when they sat under AI 모델·서비스: the hash is seen only in the browser
    await page.goto("/spotlight?tab=ai#benchmarks");
    await expect(page).toHaveURL(/\/spotlight\?tab=benchmarks$/);
    await page.goto("/spotlight?tab=ai#bench-lmarena");
    await expect(page).toHaveURL(/\/spotlight\?tab=benchmarks&site=lmarena$/);
    await expect(page.getByRole("region", { name: "LMArena" })).toBeVisible();
  });

  test("@mobile the benchmarks read on a phone", async ({ page }) => {
    await page.goto("/spotlight?tab=benchmarks");
    const bench = page.getByRole("region", { name: "AI 벤치마크" });
    const tb = bench.getByRole("table", { name: "Terminal-Bench 4.0 순위표" });
    await expect(tb.getByRole("row").nth(1)).toContainText("Claude Code");
    // body text at least 14 px
    const tbSize = await tb.getByRole("rowheader").first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(tbSize).toBeGreaterThanOrEqual(14);
    // the site menu wraps instead of pushing the page wide
    await expect(bench.getByRole("navigation", { name: "벤치마크 사이트" }).getByRole("link", { name: /ForecastBench/ })).toBeVisible();
    await page.goto("/spotlight?tab=benchmarks&site=forecastbench");
    await expect(bench.getByRole("table", { name: "ForecastBench 토너먼트 순위표" }).getByRole("row").nth(1)).toContainText("fire hedgehog");
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
