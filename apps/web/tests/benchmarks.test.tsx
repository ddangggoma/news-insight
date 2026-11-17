import { fireEvent, render, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { LiveBenchTable } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { BenchmarksSection } from "@/components/reader/benchmarks/benchmarks-section";
import { providerColor, providerKey } from "@/components/reader/benchmarks/provider-colors";
import { BENCHMARK_GROUPS, BENCHMARK_SITES, type BenchmarkRow, type BenchmarkSite, benchmarkHref, colourOrg, isOpenLicense, newestBoardFirst, parseSite } from "@/lib/benchmark-types";
import { liveBenchModels, lmArenaView, projectViews } from "@/lib/benchmark-view";
import { SPOTLIGHT_TABS, parseTab, spotlightHref } from "@/lib/spotlight-types";

beforeAll(() => {
  // Recharts' ResponsiveContainer measures its parent; jsdom has no ResizeObserver
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

const row = (over: Partial<BenchmarkRow>): BenchmarkRow => ({
  board: "main",
  model: "m",
  model_id: null,
  org: null,
  config: null,
  metric: "overall",
  value: 0,
  ci_low: null,
  ci_high: null,
  extra: {},
  rank: null,
  change: null,
  change_by: 0,
  ...over,
});

const siteOf = (over: Partial<BenchmarkSite>): BenchmarkSite => ({
  site: "livebench",
  title: "LiveBench",
  source_url: "https://livebench.ai/",
  license: "공개 데이터, 별도 라이선스 표기 없음",
  attribution: "LiveBench (Abacus.AI)",
  release: "2026-10-25",
  fetched_at: "2026-11-03T03:31:00Z",
  stale: false,
  boards: ["main"],
  rows: [],
  ...over,
});

const CATS = ["long_agentic", "design", "coding", "browser", "data_analysis", "research", "reasoning"];
function liveModel(model: string, scores: number[], rank: number | null, meta: Record<string, unknown> = {}, coverage = 1): BenchmarkRow[] {
  const cats = CATS.filter((_, i) => i < scores.length);
  const org = typeof meta.organization === "string" ? meta.organization : null;
  return [
    row({ model, org, metric: "overall", value: scores.reduce((a, b) => a + b, 0) / scores.length, rank, extra: { derived: true, categories: cats, coverage, ...meta } }),
    ...cats.map((metric, i) => row({ model, org, metric, value: scores[i], extra: { category: metric, parts: { "Sub A": scores[i] - 1 }, ...meta } })),
    ...cats.map((column, i) => row({ model, org, metric: "cost_per_success", value: 10 * (i + 1), extra: { category: column, column, questions: 10 } })),
  ];
}

const livebench = siteOf({
  rows: [
    ...liveModel("claude-opus-5.5", [72.8, 86.9, 96.3, 88.4, 80.3, 85.0, 92.2], 1, { display_name: "Claude Opus 5.5", organization: "Anthropic", open_weights: false }),
    ...liveModel("gpt-5.5", [70.0, 80.0, 99.0, 85.0, 78.0, 80.0, 90.0], 2, { display_name: "GPT-5.5", organization: "OpenAI", open_weights: false }),
    ...liveModel("deepseek-v4.1-flash", [35.7, 83.4, 96.0, 67.2, 79.5, 79.5, 89.1], 3, { display_name: "DeepSeek V4.1 Flash", organization: "DeepSeek", open_weights: true }),
    // no metadata at all: openness unknown, so not open even though the name looks like an open family
    ...liveModel("qwen3.8-27b", [30.0, 70.0, 80.0, 60.0, 70.0, 70.0, 80.0], 4),
    ...liveModel("tiny-model", [90.0, 91.0], null, {}, 0.286),
    ...liveModel("small-model", [95.0, 96.0], null, {}, 0.286),
  ],
});
const liveModels = liveBenchModels(livebench);

const firstColumn = (table: HTMLElement) =>
  within(table)
    .getAllByRole("row")
    .slice(1)
    .map((tr) => tr.querySelector("th, td")?.textContent ?? "");

describe("provider colours", () => {
  it("keeps provider colours stable", () => {
    expect(providerColor("Anthropic", "light")).toBe(providerColor("anthropic", "light"));
    expect(providerColor("Google DeepMind", "dark")).toBe(providerColor("google", "dark"));
    expect(providerColor("Anthropic", "light")).not.toBe(providerColor("OpenAI", "light"));
  });

  it("gives every provider a hue of its own", () => {
    expect(providerColor("Anthropic", "light")).toBe("oklch(62% 0.15 50)");
    expect(providerColor("OpenAI", "dark")).toBe("oklch(75% 0.14 155)");
    expect(providerColor("google", "light")).toBe("oklch(58% 0.17 255)");
    expect(providerColor("Xiaomi", "light")).toBe("oklch(65% 0.13 95)");
    // the providers that used to share a slot as outlines now have hues of their own
    const hues = ["openai", "anthropic", "google", "moonshot", "minimax", "mistral", "zai", "deepseek"].map((p) => providerColor(p, "light"));
    expect(new Set(hues).size).toBe(hues.length);
  });

  it("paints an unknown maker neutral gray", () => {
    expect(providerKey("Some Lab")).toBe("other");
    expect(providerColor("Some Lab", "light")).toBe(providerColor(null, "light"));
  });

  it("gives Moonshot, Z AI and MiniMax their own marks", () => {
    expect(providerKey("Moonshot AI")).toBe("moonshot");
    expect(providerKey("zai")).toBe("zai");
    expect(providerKey("Zhipu AI")).toBe("zai");
    expect(providerKey("MiniMax")).toBe("minimax");
  });
});

describe("helpers", () => {
  it("guesses a maker from the name only for colour", () => {
    expect(colourOrg(null, "claude-opus-5.5")).toBe("Anthropic");
    expect(colourOrg("google", "claude-x")).toBe("google");
    expect(colourOrg(null, "frob-1")).toBeNull();
  });

  it("counts a licence as open only when it names one", () => {
    expect(isOpenLicense("Apache 2.0")).toBe(true);
    expect(isOpenLicense("MIT")).toBe(true);
    for (const closed of ["Proprietary", "proprietary", "Unknown", "N/A", "", null, undefined]) expect(isOpenLicense(closed)).toBe(false);
  });

  it("puts the newest version first", () => {
    expect(newestBoardFirst(["v1", "v1.1"])).toEqual(["v1.1", "v1"]);
    expect(newestBoardFirst(["v2", "v1.1", "v1"])).toEqual(["v2", "v1.1", "v1"]);
  });

  it("computes LiveBench's cost per successful task like the site", () => {
    // (Σ cost ÷ Σ questions) ÷ overall × 100
    const opus = liveModels.find((m) => m.model === "claude-opus-5.5")!;
    const costPerTask = (10 + 20 + 30 + 40 + 50 + 60 + 70) / 70;
    expect(opus.costPerSuccess).toBeCloseTo((costPerTask / opus.overall!) * 100, 3);
  });

  it("takes LiveBench's own name, organisation and openness", () => {
    const deepseek = liveModels.find((m) => m.model === "deepseek-v4.1-flash")!;
    expect(deepseek).toMatchObject({ name: "DeepSeek V4.1 Flash", org: "DeepSeek", open: true, provider: "deepseek" });
    const qwen = liveModels.find((m) => m.model === "qwen3.8-27b")!;
    expect(qwen).toMatchObject({ name: "qwen3.8-27b", org: null, open: false, provider: "alibaba" });
  });

  it("orders LiveBench ranked first, then the unranked by overall", () => {
    expect(liveModels.map((m) => m.model)).toEqual(["claude-opus-5.5", "gpt-5.5", "deepseek-v4.1-flash", "qwen3.8-27b", "small-model", "tiny-model"]);
  });

  it("has a 벤치마크 tab right after AI 모델·서비스; the old AI 모델 tab maps to it", () => {
    const labels = SPOTLIGHT_TABS.map((tab) => tab.label);
    expect(labels).not.toContain("AI 모델");
    expect(labels.slice(labels.indexOf("AI 모델·서비스"), labels.indexOf("AI 모델·서비스") + 2)).toEqual(["AI 모델·서비스", "벤치마크"]);
    expect(parseTab("benchmarks")).toBe("benchmarks");
    expect(parseTab("models")).toBe("benchmarks");
    expect(spotlightHref("benchmarks", null)).toBe("/spotlight?tab=benchmarks");
    expect(spotlightHref("benchmarks", "2026-11-01")).toBe("/spotlight?tab=benchmarks&date=2026-11-01");
  });

  it("lists eleven sites in two groups, without DeepSWE and Artificial Analysis", () => {
    expect(BENCHMARK_GROUPS.map((g) => g.title)).toEqual(["AI 에이전트", "AI 모델"]);
    expect(BENCHMARK_GROUPS.flatMap((g) => g.sites)).toEqual([...BENCHMARK_SITES]);
    expect(BENCHMARK_SITES).toHaveLength(11);
    for (const gone of ["deepswe", "artificial_analysis"]) expect(BENCHMARK_SITES as readonly string[]).not.toContain(gone);
    for (const added of ["seal", "vals", "vending_bench", "simplebench", "forecastbench"]) expect(BENCHMARK_SITES as readonly string[]).toContain(added);
  });

  it("opens the menu's first site unless ?site= names another", () => {
    expect(parseSite(undefined)).toBe("terminal_bench");
    expect(parseSite("vals")).toBe("vals");
    expect(parseSite("deepswe")).toBe("terminal_bench");
    expect(benchmarkHref("terminal_bench")).toBe("/spotlight?tab=benchmarks");
    expect(benchmarkHref("vals")).toBe("/spotlight?tab=benchmarks&site=vals");
    expect(benchmarkHref("seal", "2026-11-01")).toBe("/spotlight?tab=benchmarks&site=seal&date=2026-11-01");
  });
});

describe("projections", () => {
  it("send the client only the fields each card draws", () => {
    expect(Object.keys(liveModels[0]).sort()).toEqual(
      ["model", "name", "org", "provider", "open", "overall", "rank", "coverage", "change", "changeBy", "scores", "parts", "costPerSuccess"].sort(),
    );
    const boards = lmArenaView(arena);
    expect(boards.map((b) => Object.keys(b).sort())).toEqual([["key", "published", "rows"], ["key", "published", "rows"]]);
    expect(Object.keys(boards[0].rows[0]).sort()).toEqual(["rank", "model", "org", "score", "low", "high", "votes", "license"].sort());
    // a moved row carries its change; an unmoved one leaves it out
    expect(boards[0].rows.find((r) => r.model === "Claude Opus 5.5")).toMatchObject({ change: "new", changeBy: 0 });
    expect(boards[0]).toMatchObject({ key: "text_style_control", published: "2026-11-02" });
  });

  it("projects only the sites it is given", () => {
    expect(Object.keys(projectViews({ livebench }))).toEqual(["livebench"]);
    expect(projectViews({})).toEqual({});
  });

  it("keeps the tab small: only the picked site's rows ride in the page", () => {
    // ~ the 2026-11-03 data of the largest site: LMArena, 837 rows over five boards
    const boards = ["text_style_control", "webdev", "vision_style_control", "search", "agent"];
    const lmarena = siteOf({
      site: "lmarena",
      boards,
      rows: [419, 152, 167, 42, 57].flatMap((n, b) =>
        Array.from({ length: n }, (_, i) =>
          row({ board: boards[b], model: `Arena Model Name ${i} (High)`, org: "google", config: "High", metric: "rating", value: 1527.5065447464403 - i * 0.731, ci_low: 1521.8137264519027 - i * 0.731, ci_high: 1533.1993630409779 - i * 0.731, rank: i + 1, extra: { rank: i + 1, vote_count: 20000, license: "Proprietary", variance: 3.1, leaderboard_publish_date: "2026-11-02" } }),
        ),
      ),
    });
    const props = JSON.stringify(projectViews({ lmarena })).length;
    const html = renderToString(<BenchmarksSection summary={null} site="lmarena" full={lmarena} note="" />).length;
    expect(props + html).toBeLessThan(250_000);
    // another site's card is not in the page at all
    expect(renderToString(<BenchmarksSection summary={null} site="lmarena" full={lmarena} note="" />)).not.toContain("LiveBench 순위표");
  });
});

describe("LiveBenchTable", () => {
  it("sorts the LiveBench table by a clicked column", () => {
    render(<LiveBenchTable models={liveModels} />);
    const table = screen.getByRole("table");
    expect(firstColumn(table)[0]).toContain("Claude Opus 5.5");
    fireEvent.click(within(table).getByRole("button", { name: /^코딩/ }));
    expect(firstColumn(table)[0]).toContain("GPT-5.5");
  });

  it("sorts cost cheapest first", () => {
    render(<LiveBenchTable models={liveModels} />);
    const table = screen.getByRole("table");
    fireEvent.click(within(table).getByRole("button", { name: /^성공 작업당 비용/ }));
    const costs = liveModels.filter((m) => m.costPerSuccess !== null).sort((a, b) => a.costPerSuccess! - b.costPerSuccess!);
    expect(firstColumn(table)[0]).toContain(costs[0].name);
  });

  it("filters LiveBench to open weights", () => {
    render(<LiveBenchTable models={liveModels} />);
    fireEvent.click(screen.getByRole("button", { name: "오픈 웨이트만" }));
    const names = firstColumn(screen.getByRole("table"));
    expect(names).toHaveLength(1);
    expect(names[0]).toContain("DeepSeek V4.1 Flash");
  });

  it("tags only models the site marks open", () => {
    render(<LiveBenchTable models={liveModels} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    const tagged = rows.filter((tr) => within(tr).queryByText("open")).map((tr) => tr.textContent);
    expect(tagged).toHaveLength(1);
    expect(tagged[0]).toContain("DeepSeek V4.1 Flash");
  });

  it("lists models the site leaves out of its table after the ranked ones, best first, marked", () => {
    render(<LiveBenchTable models={liveModels} />);
    const names = firstColumn(screen.getByRole("table"));
    expect(names.at(-2)).toContain("small-model");
    expect(names.at(-1)).toContain("tiny-model");
    expect(names.at(-1)).toContain("순위 외");
    expect(names[0]).not.toContain("순위 외");
  });

  it("prints the cost per successful task with three decimals, as the site does", () => {
    render(<LiveBenchTable models={liveModels} />);
    const opus = liveModels.find((m) => m.model === "claude-opus-5.5")!;
    expect(within(screen.getByRole("table")).getByText("$" + opus.costPerSuccess!.toFixed(3))).toBeInTheDocument();
  });

  it("expands a row into the category's sub-scores", () => {
    render(<LiveBenchTable models={liveModels} />);
    fireEvent.click(screen.getAllByRole("button", { name: "세부 점수 펼치기" })[0]);
    expect(screen.getAllByText("Sub A").length).toBeGreaterThan(0);
  });

  it("compares at most four picked models", () => {
    render(<LiveBenchTable models={liveModels} />);
    const boxes = () => screen.getAllByRole("checkbox", { name: /비교에 추가/ });
    expect(boxes()).toHaveLength(6);
    fireEvent.click(boxes()[0]);
    fireEvent.click(boxes()[1]);
    expect(screen.getByRole("region", { name: "모델 비교" })).toBeInTheDocument();
    fireEvent.click(boxes()[2]);
    fireEvent.click(boxes()[3]);
    expect(boxes().slice(0, 4).every((box) => (box as HTMLInputElement).checked)).toBe(true);
    expect(boxes()[4]).toBeDisabled();
    expect(boxes()[5]).toBeDisabled();
    fireEvent.click(boxes()[4]);
    expect(boxes()[4]).not.toBeChecked();
    // clearing one frees a slot again
    fireEvent.click(boxes()[0]);
    expect(boxes()[4]).toBeEnabled();
  });
});

const arena = siteOf({
  site: "lmarena",
  title: "LMArena",
  // first-seen order differs from the site's tab order
  boards: ["webdev", "text_style_control"],
  rows: [
    row({ board: "webdev", model: "Claude Opus 5.5", org: "anthropic", metric: "rating", value: 1600, ci_low: 1590, ci_high: 1610, rank: 1, extra: { rank: 1, vote_count: 100, license: "Proprietary" } }),
    row({ board: "text_style_control", model: "Gemini 4 Carbon (High)", org: "google", metric: "rating", value: 1512, ci_low: 1507, ci_high: 1517, rank: 1, extra: { rank: 1, vote_count: 20311, license: "Proprietary", leaderboard_publish_date: "2026-11-02" } }),
    row({ board: "text_style_control", model: "Claude Opus 5.5", org: "anthropic", metric: "rating", value: 1500, ci_low: 1494, ci_high: 1506, rank: 2, change: "new", extra: { rank: 2, vote_count: 9000, license: "Proprietary" } }),
    row({ board: "text_style_control", model: "GLM-5.3", org: "zai", metric: "rating", value: 1450, ci_low: 1440, ci_high: 1460, rank: 3, extra: { rank: 3, vote_count: 4000, license: "MIT" } }),
    row({ board: "text_style_control", model: "Qwen3.8 Max", org: "alibaba", metric: "rating", value: 1440, ci_low: 1430, ci_high: 1450, rank: 4, extra: { rank: 4, vote_count: 3000, license: "Proprietary" } }),
    row({ board: "text_style_control", model: "Mystery Model", org: null, metric: "rating", value: 1400, ci_low: 1390, ci_high: 1410, rank: 5, extra: { rank: 5, vote_count: 1000, license: "Unknown" } }),
  ],
});

describe("LmArenaTable", () => {
  it("opens on 텍스트 with the site's tab order", () => {
    render(<LmArenaTable view={lmArenaView(arena)} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["텍스트", "웹개발"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(firstColumn(screen.getByRole("table"))[0]).toContain("Gemini 4 Carbon");
  });

  it("renders an LMArena interval bar per row", () => {
    render(<LmArenaTable view={lmArenaView(arena)} />);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").length - 1;
    expect(rows).toBe(5);
    expect(within(table).getAllByRole("img", { name: /95% 신뢰구간/ })).toHaveLength(rows);
  });

  it("treats only a named licence as open", () => {
    render(<LmArenaTable view={lmArenaView(arena)} />);
    const rowOf = (name: string) => within(screen.getByRole("table")).getAllByRole("row").find((tr) => tr.textContent?.includes(name))!;
    expect(within(rowOf("GLM-5.3")).getByText("open")).toBeInTheDocument();
    expect(within(rowOf("Qwen3.8 Max")).queryByText("open")).not.toBeInTheDocument();
    expect(within(rowOf("Mystery Model")).queryByText("open")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "오픈 라이선스만" }));
    expect(firstColumn(screen.getByRole("table"))).toEqual([expect.stringContaining("GLM-5.3")]);
  });

  it("searches by name", () => {
    render(<LmArenaTable view={lmArenaView(arena)} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "모델 검색" }), { target: { value: "opus" } });
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
  });
});

describe("BenchmarksSection", () => {
  const stale = siteOf({ site: "lmarena", title: "LMArena", stale: true, boards: ["text_style_control"] });
  const summary = [stale, siteOf({ rows: [row({ model: "gpt-5.5", rank: 2, change: "new" })] })];
  const menu = () => screen.getByRole("navigation", { name: "벤치마크 사이트" });

  it("shows one site's card: the one picked in the menu", () => {
    render(<BenchmarksSection summary={summary} site="livebench" full={livebench} note="" />);
    // the section itself is a region too; the cards are the ones named by aria-label
    const cards = screen.getAllByRole("region").filter((region) => region.hasAttribute("aria-label"));
    expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual(["LiveBench"]);
    expect(within(screen.getByRole("region", { name: "LiveBench" })).getByRole("table")).toBeInTheDocument();
    expect(within(menu()).getByRole("link", { name: "LiveBench" })).toHaveAttribute("aria-current", "page");
    expect(within(menu()).getByRole("link", { name: /Vals Index/ })).not.toHaveAttribute("aria-current");
  });

  it("lists every site in the menu under its group, each addressable by ?site=", () => {
    render(<BenchmarksSection summary={summary} site="livebench" full={livebench} note="" />);
    const agents = within(menu()).getByRole("group", { name: "AI 에이전트" });
    const models = within(menu()).getByRole("group", { name: "AI 모델" });
    const names = (group: HTMLElement) =>
      within(group)
        .getAllByRole("link")
        .map((a) => a.textContent?.replace(/미수집|갱신 지연/, "") ?? "");
    expect(names(agents)).toEqual(["Terminal-Bench", "OSWorld 2.0", "τ²-bench", "Vals Index", "Vending-Bench 2"]);
    expect(names(models)).toEqual(["LiveBench", "LMArena", "Epoch AI", "Scale SEAL", "SimpleBench", "ForecastBench"]);
    expect(within(agents).getByRole("link", { name: /Terminal-Bench/ })).toHaveAttribute("href", "/spotlight?tab=benchmarks");
    expect(within(models).getByRole("link", { name: /Scale SEAL/ })).toHaveAttribute("href", "/spotlight?tab=benchmarks&site=seal");
    expect(screen.queryByText(/DeepSWE|Artificial Analysis/)).not.toBeInTheDocument();
  });

  it("keeps the picked day in the menu's links", () => {
    render(<BenchmarksSection summary={summary} site="livebench" full={livebench} note="" date="2026-11-01" />);
    expect(within(menu()).getByRole("link", { name: /Epoch AI/ })).toHaveAttribute("href", "/spotlight?tab=benchmarks&site=epoch&date=2026-11-01");
  });

  it("marks a stale site and one never collected in the menu", () => {
    render(<BenchmarksSection summary={summary} site="lmarena" full={null} note="" />);
    expect(within(menu()).getByRole("link", { name: /LMArena/ })).toHaveTextContent("갱신 지연");
    expect(within(menu()).getByRole("link", { name: /Epoch AI/ })).toHaveTextContent("미수집");
    expect(within(menu()).getByRole("link", { name: "LiveBench" })).not.toHaveTextContent(/갱신 지연|미수집/);
    expect(within(screen.getByRole("region", { name: "LMArena" })).getByText("갱신 지연")).toBeInTheDocument();
  });

  it("says so when the picked site was never collected", () => {
    render(<BenchmarksSection summary={summary} site="forecastbench" full={null} note="" />);
    expect(within(screen.getByRole("region", { name: "ForecastBench" })).getByText("아직 수집된 순위가 없습니다.")).toBeInTheDocument();
  });

  it("falls back to the summary's rows when the site's full rows did not load", () => {
    render(<BenchmarksSection summary={[livebench]} site="livebench" full={null} note="" />);
    expect(within(screen.getByRole("region", { name: "LiveBench" })).getByRole("table")).toBeInTheDocument();
  });

  it("shows Opus's note and today's new models, each linking to its site", () => {
    render(<BenchmarksSection summary={summary} site="lmarena" full={null} note="오늘은 오픈 모델이 약진했습니다" />);
    expect(screen.getByText("오늘은 오픈 모델이 약진했습니다")).toBeInTheDocument();
    expect(screen.getByText("오늘의 순위 변화 (Opus)")).toBeInTheDocument();
    const arrival = within(screen.getByRole("list", { name: "새로 등장한 모델" })).getByRole("link", { name: /gpt-5\.5/ });
    expect(arrival).toHaveAttribute("href", "/spotlight?tab=benchmarks&site=livebench");
  });

  it("dates the note of a past day, since the leaderboards are always the latest", () => {
    render(<BenchmarksSection summary={summary} site="livebench" full={livebench} note="지난 메모" noteDate="2026-11-01" />);
    expect(screen.getByText(/2026년 11월 1일.*순위 변화 \(Opus\) · 아래 순위표는 최신 기준/)).toBeInTheDocument();
  });

  it("works without the summary", () => {
    render(<BenchmarksSection summary={null} site="livebench" full={livebench} note="" />);
    expect(screen.queryByRole("list", { name: "새로 등장한 모델" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "LiveBench" })).getByRole("table")).toBeInTheDocument();
  });

  it("sits under one 「AI 벤치마크」 heading that old #benchmarks links land on", () => {
    render(<BenchmarksSection summary={summary} site="livebench" full={livebench} note="" />);
    const heading = screen.getByRole("heading", { level: 2, name: "AI 벤치마크" });
    expect(heading.closest("section")).toHaveAttribute("id", "benchmarks");
    expect(screen.getByRole("heading", { level: 3, name: /LiveBench/ })).toBeInTheDocument();
  });

  it("gives the card its source link, licence, attribution and update time", () => {
    render(<BenchmarksSection summary={summary} site="livebench" full={livebench} note="" />);
    const card = screen.getByRole("region", { name: "LiveBench" });
    expect(within(card).getByRole("link", { name: /원본/ })).toHaveAttribute("href", "https://livebench.ai/");
    expect(within(card).getByText("라이선스: 공개 데이터, 별도 라이선스 표기 없음")).toBeInTheDocument();
    expect(within(card).getByText(/출처: LiveBench \(Abacus\.AI\)/)).toBeInTheDocument();
    expect(within(card).getByText(/^갱신 /)).toBeInTheDocument();
  });
});
