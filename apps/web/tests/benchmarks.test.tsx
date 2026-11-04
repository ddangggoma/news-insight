import { fireEvent, render, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { ArtificialAnalysisCharts } from "@/components/reader/benchmarks/artificial-analysis";
import { DeepSweChart } from "@/components/reader/benchmarks/deepswe";
import { buildPlot, defaultConfigs, displayName, family, formatCost, modelShades, niceTicks, toHsl } from "@/components/reader/benchmarks/deepswe-plot";
import { LiveBenchTable } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { ModelsTab } from "@/components/reader/benchmarks/models-tab";
import { providerColor, providerKey } from "@/components/reader/benchmarks/provider-colors";
import { type BenchmarkRow, type BenchmarkSite, colourOrg, isOpenLicense, newestBoardFirst } from "@/lib/benchmark-types";
import { aaModels, deepSweView, liveBenchModels, lmArenaView, projectViews } from "@/lib/benchmark-view";
import { SPOTLIGHT_TABS, parseTab } from "@/lib/spotlight-types";

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
    .map((tr) => within(tr).getAllByRole("cell")[0].textContent ?? "");

describe("provider colours", () => {
  it("keeps provider colours stable", () => {
    expect(providerColor("Anthropic", "light")).toBe(providerColor("anthropic", "light"));
    expect(providerColor("Google DeepMind", "dark")).toBe(providerColor("google", "dark"));
    expect(providerColor("Anthropic", "light")).not.toBe(providerColor("OpenAI", "light"));
  });

  it("uses DeepSWE's family hues, one per provider", () => {
    expect(providerColor("Anthropic", "light")).toBe("oklch(62% 0.15 50)");
    expect(providerColor("OpenAI", "dark")).toBe("oklch(75% 0.14 155)");
    expect(providerColor("google", "light")).toBe("oklch(58% 0.17 255)");
    expect(providerColor("Xiaomi", "light")).toBe("oklch(65% 0.13 95)");
    // the providers that used to share a slot as outlines now have hues of their own
    const hues = ["openai", "anthropic", "google", "moonshot", "minimax", "mistral", "zai", "deepseek"].map((p) => providerColor(p, "light"));
    expect(new Set(hues).size).toBe(hues.length);
    expect(toHsl(providerColor("anthropic", "light"))[0]).toBeGreaterThan(15);
    expect(toHsl(providerColor("anthropic", "light"))[0]).toBeLessThan(45);
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

  it("adds the AI model tab", () => {
    expect(SPOTLIGHT_TABS.some((tab) => tab.key === "models" && tab.label === "AI 모델")).toBe(true);
    expect(parseTab("models")).toBe("models");
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
    expect(Object.keys(deepSweView(deepswe).points[0]).sort()).toEqual(
      ["id", "board", "model", "effort", "provider", "score", "low", "high", "cost", "tokens", "steps", "harness", "best", "change", "changeBy"].sort(),
    );
    expect(Object.keys(aaModels(aa)[0]).sort()).toEqual(["model", "org", "provider", "intelligence", "price", "speed"].sort());
  });

  it("drops Artificial Analysis metrics no chart plots", () => {
    const site = siteOf({ site: "artificial_analysis", rows: [row({ model: "A", metric: "hle", value: 0.4 })] });
    expect(aaModels(site)).toEqual([]);
  });

  it("keeps the tab small with leaderboards at today's size", () => {
    // ~ the 2026-11-03 data: DeepSWE 70 + 29 rows, LiveBench 32 models, LMArena 837 rows
    const big = {
      deepswe: siteOf({
        site: "deepswe",
        boards: ["v1.1", "v1"],
        rows: Array.from({ length: 99 }, (_, i) =>
          row({ board: i < 70 ? "v1.1" : "v1", model: `model-${i}`, config: "high", metric: "pass_at_1", value: 0.7004504504504504, ci_low: 0.6721849259146309, ci_high: 0.7287159749862699, rank: i, extra: { mean_cost_usd: 6.605861326576576, mean_output_tokens: 46977.0472972973, mean_agent_steps: 78.96396396396396, harness: "mini-swe-agent", config: "x".repeat(40), cost_basis: "y".repeat(80) } }),
        ),
      }),
      livebench: siteOf({ rows: Array.from({ length: 32 }, (_, i) => liveModel(`livebench-model-${i}`, [70, 80, 90, 60, 70, 80, 90], i + 1, { display_name: `Model ${i}`, organization: "Org", open_weights: false })).flat() }),
      lmarena: siteOf({
        site: "lmarena",
        boards: ["text_style_control", "webdev", "vision_style_control", "search_style_control", "agent"],
        rows: [419, 152, 167, 42, 57].flatMap((n, b) =>
          Array.from({ length: n }, (_, i) =>
            row({ board: ["text_style_control", "webdev", "vision_style_control", "search_style_control", "agent"][b], model: `Arena Model Name ${i} (High)`, org: "google", config: "High", metric: "rating", value: 1527.5065447464403 - i * 0.731, ci_low: 1521.8137264519027 - i * 0.731, ci_high: 1533.1993630409779 - i * 0.731, rank: i + 1, extra: { rank: i + 1, vote_count: 20000, license: "Proprietary", variance: 3.1, leaderboard_publish_date: "2026-11-02" } }),
          ),
        ),
      }),
    };
    const props = JSON.stringify(projectViews(big)).length;
    const html = renderToString(<ModelsTab summary={null} sites={big} note="" />).length;
    // measured 164 KB of props + 146 KB of HTML on this data (2026-11-03)
    expect(props + html).toBeLessThan(350_000);
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

  it("lists models under the coverage bar after the ranked ones, best first, with their coverage", () => {
    render(<LiveBenchTable models={liveModels} />);
    const names = firstColumn(screen.getByRole("table"));
    expect(names.at(-2)).toContain("small-model");
    expect(names.at(-1)).toContain("tiny-model");
    expect(names.at(-1)).toContain("29%");
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

const dsRow = (over: Partial<BenchmarkRow>) => row({ board: "v1.1", metric: "pass_at_1", ...over });
const deepswe = siteOf({
  site: "deepswe",
  title: "DeepSWE",
  // the older board first, as the collector may store it
  boards: ["v1", "v1.1"],
  rows: [
    dsRow({ board: "v1", model: "old-model", value: 0.3, ci_low: 0.25, ci_high: 0.35, rank: 1, extra: { mean_cost_usd: 1 } }),
    dsRow({ model: "gpt-5-5", org: "OpenAI", config: "xhigh", value: 0.7, ci_low: 0.67, ci_high: 0.73, rank: 1, extra: { mean_cost_usd: 6.6, mean_output_tokens: 46977, mean_agent_steps: 79, harness: "mini-swe-agent" } }),
    dsRow({ model: "gpt-5-5", org: "OpenAI", config: "high", value: 0.62, ci_low: 0.58, ci_high: 0.66, extra: { mean_cost_usd: 4.5, mean_output_tokens: 30000, mean_agent_steps: 70 } }),
    dsRow({ model: "glm-5-2", config: null, value: 0.4, ci_low: 0.35, ci_high: 0.45, rank: 2, extra: { mean_cost_usd: 1.2, mean_output_tokens: 20000, mean_agent_steps: 60 } }),
  ],
});

describe("DeepSweChart", () => {
  it("opens on the newest version", () => {
    render(<DeepSweChart view={deepSweView(deepswe)} />);
    const versions = within(screen.getByRole("group", { name: "버전" })).getAllByRole("button");
    expect(versions.map((b) => b.textContent)).toEqual(["v1.1", "v1"]);
    expect(versions[0]).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("old-model")).not.toBeInTheDocument();
    fireEvent.click(versions[1]);
    expect(within(screen.getByRole("table")).getByText("old-model")).toBeInTheDocument();
  });

  it("shows each model's best effort until every effort level is asked for", () => {
    render(<DeepSweChart view={deepSweView(deepswe)} />);
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "모든 추론 강도" }));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(4);
    expect(screen.getByText("70.0")).toBeInTheDocument();
    expect(screen.getByText("±3.0")).toBeInTheDocument();
  });

  it("switches the x axis", () => {
    render(<DeepSweChart view={deepSweView(deepswe)} />);
    const toggle = within(screen.getByRole("group", { name: "가로축" })).getByRole("button", { name: "출력 토큰" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("작업당 평균 출력 토큰")).toBeInTheDocument();
  });
});

// a small v1.1 board shaped like the site's: several effort levels per model, out of order
const sweep = (model: string, levels: [string | null, number, number][], extra: Record<string, unknown> = {}) =>
  levels.map(([config, pass, cost]) =>
    dsRow({ model, config, value: pass, ci_low: pass - 0.03, ci_high: pass + 0.03, extra: { mean_cost_usd: cost, mean_output_tokens: cost * 10_000, mean_agent_steps: 30, harness: "mini-swe-agent", n_tasks_attempted: 113, ...extra } }),
  );
const board = siteOf({
  site: "deepswe",
  title: "DeepSWE",
  boards: ["v1.1"],
  release: "2026-09-22",
  rows: [
    ...sweep("gpt-5-5", [["high", 0.64, 5.1], ["max", 0.66, 9], ["low", 0.27, 1.2], ["medium", 0.54, 2.75], ["xhigh", 0.67, 7.23]]),
    ...sweep("claude-opus-5", [["low", 0.58, 1.66], ["max", 0.736, 11.84], ["high", 0.728, 6.08]]),
    ...sweep("claude-fable-5", [["high", 0.686, 9.18], ["max", 0.697, 21.63]]),
    ...sweep("glm-5-3-flash", [[null, 0.63, 0.48]]),
    ...sweep("gpt-5-4", [["xhigh", 0.518, 5.65]]),
    ...sweep("tiny-model", [["high", 0.03, 0.2]]),
  ],
});
const boardView = deepSweView(board);
const v11 = boardView.points;

describe("DeepSWE chart rules", () => {
  it("names models like the site", () => {
    expect(displayName("gpt-5-6-sol")).toBe("gpt-5.6-sol");
    expect(displayName("glm-5-3-flash")).toBe("glm-5.3-flash");
    expect(displayName("qwen3-8-max")).toBe("qwen3.8-max");
    expect(displayName("gemini-3-1-pro-preview")).toBe("gemini-3.1-pro");
    expect(displayName("gpt-6-astra")).toBe("gpt-6-astra");
  });

  it("colours by the maker in the name, each next model of a maker a lighter step", () => {
    expect(family("gpt-6-astra")).toBe("openai");
    expect(family("muse-spark-1-1")).toBe("meta");
    expect(family("glm-5-3")).toBe("zai");
    expect(family("mimo-v2-5-pro")).toBe("xiaomi");
    expect(family("frob-1")).toBe("other");
    const shades = modelShades(v11);
    expect(shades.get("claude-opus-5")!.light).toBe(providerColor("anthropic", "light"));
    expect(shades.get("claude-fable-5")!.light).not.toBe(shades.get("claude-opus-5")!.light);
    expect(shades.get("claude-fable-5")!.dark).not.toBe(shades.get("claude-opus-5")!.dark);
  });

  it("steps lower-ranked models lighter in the dark theme too, so they stay visible on the dark card", () => {
    const many = ["gpt-a", "gpt-b", "gpt-c", "gpt-d", "gpt-e", "gpt-f"].map((model, i) => ({ model, score: 70 - i }));
    const shades = modelShades(many);
    const base = toHsl(providerColor("openai", "dark"))[2];
    const lightness = many.map((m) => toHsl(shades.get(m.model)!.dark)[2]);
    for (const l of lightness.slice(1)) expect(l).toBeGreaterThan(base);
    expect(Math.max(...lightness)).toBeLessThanOrEqual(82.05);
    expect(toHsl(shades.get("gpt-b")!.light)[2]).toBeGreaterThan(toHsl(providerColor("openai", "light"))[2]);
  });

  it("keeps two close labels apart and draws a leader to a far one", () => {
    const crowd = ["aaa-1", "bbb-1", "ccc-1", "ddd-1", "eee-1", "fff-1", "ggg-1"].map((model, i) => dsRow({ model, config: "high", value: 0.5 + i * 0.001, extra: { mean_cost_usd: 3 + i * 0.01, harness: "h" } }));
    const plot = buildPlot(deepSweView(siteOf({ site: "deepswe", boards: ["v1.1"], rows: crowd })).points, "cost", null)!;
    const [a, b] = plot.labels;
    const overlapX = Math.min(a.box.x + a.box.w, b.box.x + b.box.w) - Math.max(a.box.x, b.box.x);
    const overlapY = Math.min(a.box.y + a.box.h, b.box.y + b.box.h) - Math.max(a.box.y, b.box.y);
    expect(overlapX <= 0 || overlapY <= 0).toBe(true);
    expect(plot.labels.some((l) => l.leader)).toBe(true);
    expect(plot.labels[0].leader).toBe(false);
  });

  it("uses the narrow frame under 640 px", () => {
    const plot = buildPlot(v11, "cost", 400)!;
    expect(plot.dims).toMatchObject({ mobile: true, W: 440, H: 500 });
    expect(plot.yTicks).toEqual([0, 0.2, 0.4, 0.6, 0.8]);
    // about four ticks instead of six
    expect(plot.xTicks).toEqual([0, 10, 20]);
    expect(buildPlot(v11, "cost", 1000)!.dims).toMatchObject({ mobile: false, W: 1000, H: 625 });
  });

  it("joins a model's configurations in effort order, one line per swept model", () => {
    const plot = buildPlot(v11, "cost", null)!;
    const ids = (model: string) => v11.filter((p) => p.model === model);
    const gpt = plot.lines.find((l) => l.model === "gpt-5-5")!;
    expect(gpt.ids.map((id) => ids("gpt-5-5").find((p) => p.id === id)!.effort)).toEqual(["low", "medium", "high", "xhigh", "max"]);
    expect(plot.lines.map((l) => l.model).sort()).toEqual(["claude-fable-5", "claude-opus-5", "gpt-5-5"]);
    expect(plot.lines.find((l) => l.model === "glm-5-3-flash")).toBeUndefined();
  });

  it("labels each model's default effort, else its highest", () => {
    const plot = buildPlot(v11, "cost", null)!;
    const labelled = (model: string) => plot.points.filter((p) => p.model === model && p.labeled).map((p) => p.effort);
    expect(labelled("gpt-5-5")).toEqual(["medium"]);
    expect(labelled("claude-fable-5")).toEqual(["high"]);
    expect(labelled("claude-opus-5")).toEqual(["max"]);
    expect(labelled("glm-5-3-flash")).toEqual([null]);
    expect(plot.labels).toHaveLength(6);
    expect(plot.labels.find((l) => l.model === "glm-5-3-flash")).toMatchObject({ line1: "glm-5.3-flash", line2: null });
  });

  it("runs the x axis from dear to cheap with nice ticks", () => {
    expect(niceTicks(13.94)).toEqual([0, 5, 10]);
    expect(niceTicks(52_000)).toEqual([0, 10_000, 20_000, 30_000, 40_000, 50_000]);
    expect([formatCost(0), formatCost(5), formatCost(10), formatCost(0.005)]).toEqual(["$0", "$5.00", "$10", "$0.005"]);
    const plot = buildPlot(v11, "cost", null)!;
    const at = (model: string, effort: string) => plot.points.find((p) => p.model === model && p.effort === effort)!;
    expect(at("gpt-5-5", "low").px).toBeGreaterThan(at("gpt-5-5", "max").px);
    expect(plot.xTicks).toEqual([0, 5, 10, 15, 20]);
    expect(plot.yTicks).toEqual([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]);
    // every label inside the frame
    for (const l of plot.labels) expect(l.x).toBeGreaterThan(0);
  });

  it("opens with the site's default configurations", () => {
    const shown = defaultConfigs(v11);
    const models = (ids: Set<string>) => new Set(v11.filter((p) => ids.has(p.id)).map((p) => p.model));
    // gpt-5-4 is in the hidden set, tiny-model under 5%, fable's $21.63 max above $15
    expect([...models(shown)].sort()).toEqual(["claude-fable-5", "claude-opus-5", "glm-5-3-flash", "gpt-5-5"]);
    expect(v11.filter((p) => shown.has(p.id)).some((p) => p.cost! > 15)).toBe(false);
    expect(shown.size).toBe(10);
  });

  it("carries the task count and the snapshot day", () => {
    expect(boardView.info["v1.1"]).toEqual({ tasks: 113, updated: "2026-09-22" });
  });
});

describe("DeepSWE chart", () => {
  const svg = () => screen.getByRole("group", { name: /DeepSWE 점수와/ });

  it("draws dots, effort lines and labels without error bars or a frontier", () => {
    render(<DeepSweChart view={boardView} />);
    const chart = svg();
    // fable's $21.63 max starts hidden, so fable is a lone dot
    expect(chart.querySelectorAll("[data-line]")).toHaveLength(2);
    expect(chart.querySelectorAll("[data-point]")).toHaveLength(10);
    expect(within(chart).getByText("gpt-5.5")).toBeInTheDocument();
    expect(within(chart).getByText("MEDIUM")).toBeInTheDocument();
    expect(within(chart).queryByText("gpt-5.4")).not.toBeInTheDocument();
    expect(within(chart).getByText("효율 높음 ↗")).toBeInTheDocument();
    expect(document.querySelector(".recharts-wrapper, .recharts-errorBar")).toBeNull();
    expect(screen.queryByText(/효율 경계/)).not.toBeInTheDocument();
    expect(screen.getByText("과제 113개")).toBeInTheDocument();
  });

  it("counts shown configurations and toggles a model's", () => {
    render(<DeepSweChart view={boardView} />);
    const picker = screen.getByRole("button", { name: "구성 고르기" });
    expect(picker).toHaveTextContent("(10/13)");
    fireEvent.click(picker);
    fireEvent.click(screen.getByRole("checkbox", { name: /gpt-5\.4/ }));
    expect(picker).toHaveTextContent("(11/13)");
    expect(within(svg()).getByText("gpt-5.4")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /gpt-5\.5/ }));
    expect(picker).toHaveTextContent("(6/13)");
    expect(svg().querySelector('[data-line="gpt-5-5"]')).toBeNull();
  });

  it("picks out the hovered model and pins it on click", () => {
    render(<DeepSweChart view={boardView} />);
    const chart = svg();
    const point = (model: string) => chart.querySelector<SVGGElement>(`[data-point="${model}"]`)!;
    fireEvent.mouseEnter(point("gpt-5-5"));
    expect(point("claude-opus-5").style.opacity).toBe("0.55");
    expect(point("claude-opus-5").style.filter).toBe("grayscale(1)");
    expect(point("gpt-5-5").style.opacity).toBe("");
    // the crosshair reads the exact pass rate off the y axis
    expect(within(chart).getAllByText("64%").length).toBeGreaterThan(0);
    fireEvent.click(point("gpt-5-5"));
    fireEvent.mouseLeave(point("gpt-5-5"));
    expect(point("claude-opus-5").style.opacity).toBe("0.55");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(point("claude-opus-5").style.opacity).toBe("");
  });

  it("tells screen readers the table has the same data and lets the keyboard pick a model", () => {
    render(<DeepSweChart view={boardView} />);
    const chart = svg();
    expect(chart).toHaveAccessibleDescription(/아래 DeepSWE 순위표/);
    const point = within(chart).getByRole("button", { name: /^gpt-5\.5 medium: pass@1 54\.0%/ });
    expect(point).toHaveAttribute("tabindex", "0");
    // one focusable point per model, the labelled one
    expect(within(chart).getAllByRole("button")).toHaveLength(4);
    const other = () => chart.querySelector<SVGGElement>('[data-point="claude-opus-5"]')!;
    fireEvent.focus(point);
    expect(other().style.opacity).toBe("0.55");
    fireEvent.keyDown(point, { key: "Enter" });
    expect(point).toHaveAttribute("aria-pressed", "true");
    fireEvent.blur(point);
    expect(other().style.opacity).toBe("0.55");
    fireEvent.keyDown(point, { key: "Escape" });
    expect(point).toHaveAttribute("aria-pressed", "false");
    expect(other().style.opacity).toBe("");
  });

  it("puts a pass@1 bar with its interval on every table row", () => {
    render(<DeepSweChart view={boardView} />);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").length - 1;
    expect(within(table).getAllByRole("img", { name: /^pass@1 / })).toHaveLength(rows);
    expect(within(table).getByText("80%")).toBeInTheDocument();
  });
});

const aa = siteOf({
  site: "artificial_analysis",
  title: "Artificial Analysis",
  source_url: "https://artificialanalysis.ai/",
  attribution: "Data: Artificial Analysis",
  boards: ["language"],
  rows: [
    row({ board: "language", model: "GLM-5.3 (Max)", org: "Z AI", metric: "artificial_analysis_intelligence_index", value: 31.7, rank: 1 }),
    row({ board: "language", model: "GLM-5.3 (Max)", org: "Z AI", metric: "price_1m_blended_3_to_1", value: 2.15 }),
    row({ board: "language", model: "GLM-5.3 (Max)", org: "Z AI", metric: "median_output_tokens_per_second", value: 80 }),
  ],
});

describe("ArtificialAnalysisCharts", () => {
  it("credits Artificial Analysis", () => {
    render(<ArtificialAnalysisCharts models={aaModels(aa)} sourceUrl={aa.source_url} attribution={aa.attribution} />);
    const link = screen.getByRole("link", { name: "Data: Artificial Analysis" });
    expect(link).toHaveAttribute("href", "https://artificialanalysis.ai/");
  });
});

describe("ModelsTab", () => {
  const summary = [siteOf({ site: "deepswe", title: "DeepSWE", stale: true, boards: ["v1.1"] }), siteOf({ rows: [row({ model: "gpt-5.5", rank: 2, change: "new" })] })];

  it("marks a stale site", () => {
    render(<ModelsTab summary={summary} sites={{ deepswe, livebench }} note="" />);
    const card = screen.getByRole("region", { name: "DeepSWE" });
    expect(within(card).getByText("갱신 지연")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "LiveBench" })).queryByText("갱신 지연")).not.toBeInTheDocument();
  });

  it("shows Opus's note, today's new models and a missing key", () => {
    render(<ModelsTab summary={summary} sites={{ deepswe, livebench }} note="오늘은 오픈 모델이 약진했습니다" />);
    expect(screen.getByText("오늘은 오픈 모델이 약진했습니다")).toBeInTheDocument();
    expect(screen.getByText("오늘의 순위 변화 (Opus)")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "새로 등장한 모델" })).getByText(/gpt-5\.5/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Artificial Analysis" })).getByText("키 미설정")).toBeInTheDocument();
  });

  it("dates the note of a past day, since the leaderboards are always the latest", () => {
    render(<ModelsTab summary={summary} sites={{ deepswe, livebench }} note="지난 메모" noteDate="2026-11-01" />);
    expect(screen.getByText(/2026년 11월 1일.*순위 변화 \(Opus\) · 아래 순위표는 최신 기준/)).toBeInTheDocument();
  });

  it("works without the summary", () => {
    render(<ModelsTab summary={null} sites={{ deepswe, livebench }} note="" />);
    expect(screen.queryByRole("list", { name: "새로 등장한 모델" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "LiveBench" })).getByRole("table")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "LiveBench" })).getByRole("link", { name: /원본/ })).toBeInTheDocument();
  });

  it("gives every card its source link and update time", () => {
    render(<ModelsTab summary={summary} sites={{ deepswe, livebench }} note="" />);
    const card = screen.getByRole("region", { name: "LiveBench" });
    expect(within(card).getByRole("link", { name: /원본/ })).toHaveAttribute("href", "https://livebench.ai/");
    expect(within(card).getByText(/LiveBench \(Abacus\.AI\)/)).toBeInTheDocument();
  });
});
