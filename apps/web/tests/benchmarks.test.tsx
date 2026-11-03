import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { ArtificialAnalysisCharts } from "@/components/reader/benchmarks/artificial-analysis";
import { DeepSweChart } from "@/components/reader/benchmarks/deepswe";
import { paretoFrontier } from "@/components/reader/benchmarks/frontier";
import { LiveBenchTable, liveBenchModels } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { ModelsTab } from "@/components/reader/benchmarks/models-tab";
import { providerColor, providerKey } from "@/components/reader/benchmarks/provider-colors";
import { type BenchmarkRow, type BenchmarkSite, forClient, isOpenWeights, openWeightsIndex, rowOrg } from "@/lib/benchmark-types";
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
function liveModel(model: string, scores: number[], rank: number | null, coverage = 1): BenchmarkRow[] {
  const cats = CATS.filter((_, i) => i < scores.length);
  return [
    row({ model, metric: "overall", value: scores.reduce((a, b) => a + b, 0) / scores.length, rank, extra: { derived: true, categories: cats, coverage } }),
    ...cats.map((metric, i) => row({ model, metric, value: scores[i], extra: { category: metric, parts: { "Sub A": scores[i] - 1 } } })),
    ...cats.map((column, i) => row({ model, metric: "cost_per_success", value: 10 * (i + 1), extra: { category: column, column, questions: 10 } })),
  ];
}

const livebench = siteOf({
  rows: [
    ...liveModel("claude-opus-5.5", [72.8, 86.9, 96.3, 88.4, 80.3, 85.0, 92.2], 1),
    ...liveModel("gpt-5.5", [70.0, 80.0, 99.0, 85.0, 78.0, 80.0, 90.0], 2),
    ...liveModel("deepseek-v4.1-flash", [35.7, 83.4, 96.0, 67.2, 79.5, 79.5, 89.1], 3),
    ...liveModel("tiny-model", [90.0, 91.0], null, 0.286),
  ],
});

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

  it("paints an unknown maker neutral gray", () => {
    expect(providerKey("Some Lab")).toBe("other");
    expect(providerColor("Some Lab", "light")).toBe(providerColor(null, "light"));
  });
});

describe("helpers", () => {
  it("computes the efficiency frontier", () => {
    expect(paretoFrontier([{ id: "a", x: 1, y: 50 }, { id: "b", x: 2, y: 40 }, { id: "c", x: 3, y: 70 }])).toEqual(["a", "c"]);
    expect(paretoFrontier([{ id: "a", x: 1, y: 50 }, { id: "b", x: 1, y: 60 }, { id: "c", x: Number.NaN, y: 99 }])).toEqual(["b"]);
  });

  it("reads the maker off the name when the site leaves it out", () => {
    expect(rowOrg({ org: null, model: "claude-opus-5.5" })).toBe("Anthropic");
    expect(rowOrg({ org: "google", model: "claude-x" })).toBe("google");
    expect(rowOrg({ org: null, model: "frob-1" })).toBeNull();
  });

  it("borrows open weights from LMArena licences and AA, by id and spelling", () => {
    const index = openWeightsIndex([
      siteOf({ site: "lmarena", rows: [row({ model: "Beam 1.0 (Max)", model_id: 9, extra: { license: "Apache 2.0" } }), row({ model: "Claude X", extra: { license: "Proprietary" } })] }),
    ]);
    expect(isOpenWeights({ model: "beam-1.0", model_id: null }, index)).toBe(true);
    expect(isOpenWeights({ model: "whatever", model_id: 9 }, index)).toBe(true);
    expect(isOpenWeights({ model: "claude-x", model_id: null }, index)).toBe(false);
    expect(isOpenWeights({ model: "qwen3.8-27b", model_id: null }, index)).toBe(true);
  });

  it("ships only the plotted Artificial Analysis metrics", () => {
    const site = siteOf({
      site: "artificial_analysis",
      rows: [row({ metric: "artificial_analysis_intelligence_index" }), row({ metric: "hle" }), row({ metric: "price_1m_blended_3_to_1" })],
    });
    expect(forClient(site).rows.map((r) => r.metric)).toEqual(["artificial_analysis_intelligence_index", "price_1m_blended_3_to_1"]);
  });

  it("computes LiveBench's cost per successful task like the site", () => {
    // (Σ cost ÷ Σ questions) ÷ overall × 100
    const opus = liveBenchModels(livebench, new Set()).find((m) => m.model === "claude-opus-5.5")!;
    const costPerTask = (10 + 20 + 30 + 40 + 50 + 60 + 70) / 70;
    expect(opus.costPerSuccess).toBeCloseTo((costPerTask / opus.overall!) * 100, 6);
  });

  it("adds the AI model tab", () => {
    expect(SPOTLIGHT_TABS.some((tab) => tab.key === "models" && tab.label === "AI 모델")).toBe(true);
    expect(parseTab("models")).toBe("models");
  });
});

describe("LiveBenchTable", () => {
  it("sorts the LiveBench table by a clicked column", () => {
    render(<LiveBenchTable site={livebench} openIndex={new Set()} />);
    const table = screen.getByRole("table");
    expect(firstColumn(table)[0]).toContain("claude-opus-5.5");
    fireEvent.click(within(table).getByRole("button", { name: /^코딩/ }));
    expect(firstColumn(table)[0]).toContain("gpt-5.5");
  });

  it("filters LiveBench to open weights", () => {
    render(<LiveBenchTable site={livebench} openIndex={new Set()} />);
    fireEvent.click(screen.getByRole("button", { name: "오픈 웨이트만" }));
    const names = firstColumn(screen.getByRole("table"));
    expect(names).toHaveLength(1);
    expect(names[0]).toContain("deepseek-v4.1-flash");
  });

  it("lists a model under the coverage bar after the ranked ones, with its coverage", () => {
    render(<LiveBenchTable site={livebench} openIndex={new Set()} />);
    const names = firstColumn(screen.getByRole("table"));
    expect(names.at(-1)).toContain("tiny-model");
    expect(names.at(-1)).toContain("29%");
  });

  it("expands a row into the category's sub-scores", () => {
    render(<LiveBenchTable site={livebench} openIndex={new Set()} />);
    fireEvent.click(screen.getAllByRole("button", { name: "세부 점수 펼치기" })[0]);
    expect(screen.getAllByText("Sub A").length).toBeGreaterThan(0);
  });

  it("compares at most four picked models", () => {
    render(<LiveBenchTable site={livebench} openIndex={new Set()} />);
    const boxes = screen.getAllByRole("checkbox", { name: /비교에 추가/ });
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    expect(screen.getByRole("region", { name: "모델 비교" })).toBeInTheDocument();
  });
});

const arena = siteOf({
  site: "lmarena",
  title: "LMArena",
  boards: ["text_style_control", "webdev"],
  rows: [
    row({ board: "text_style_control", model: "Gemini 4 Carbon (High)", org: "google", metric: "rating", value: 1512, ci_low: 1507, ci_high: 1517, rank: 1, extra: { rank: 1, vote_count: 20311, license: "Proprietary" } }),
    row({ board: "text_style_control", model: "Claude Opus 5.5", org: "anthropic", metric: "rating", value: 1500, ci_low: 1494, ci_high: 1506, rank: 2, change: "new", extra: { rank: 2, vote_count: 9000, license: "Proprietary" } }),
    row({ board: "text_style_control", model: "GLM-5.3", org: "zhipu", metric: "rating", value: 1450, ci_low: 1440, ci_high: 1460, rank: 3, extra: { rank: 3, vote_count: 4000, license: "MIT" } }),
    row({ board: "webdev", model: "Claude Opus 5.5", org: "anthropic", metric: "rating", value: 1600, ci_low: 1590, ci_high: 1610, rank: 1, extra: { rank: 1, vote_count: 100, license: "Proprietary" } }),
  ],
});

describe("LmArenaTable", () => {
  it("renders an LMArena interval bar per row", () => {
    render(<LmArenaTable site={arena} />);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").length - 1;
    expect(rows).toBe(3);
    expect(within(table).getAllByRole("img", { name: /95% 신뢰구간/ })).toHaveLength(rows);
  });

  it("filters to open licences and searches by name", () => {
    render(<LmArenaTable site={arena} />);
    fireEvent.click(screen.getByRole("button", { name: "오픈 라이선스만" }));
    expect(firstColumn(screen.getByRole("table"))).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "오픈 라이선스만" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "모델 검색" }), { target: { value: "opus" } });
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
  });

  it("labels the boards in Korean", () => {
    render(<LmArenaTable site={arena} />);
    expect(screen.getByRole("tab", { name: "텍스트" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "웹개발" })).toBeInTheDocument();
  });
});

const deepswe = siteOf({
  site: "deepswe",
  title: "DeepSWE",
  boards: ["v1.1"],
  rows: [
    row({ board: "v1.1", model: "gpt-5-5", org: "OpenAI", config: "xhigh", metric: "pass_at_1", value: 0.7, ci_low: 0.67, ci_high: 0.73, rank: 1, extra: { mean_cost_usd: 6.6, mean_output_tokens: 46977, mean_agent_steps: 79 } }),
    row({ board: "v1.1", model: "gpt-5-5", org: "OpenAI", config: "high", metric: "pass_at_1", value: 0.62, ci_low: 0.58, ci_high: 0.66, extra: { mean_cost_usd: 4.5, mean_output_tokens: 30000, mean_agent_steps: 70 } }),
    row({ board: "v1.1", model: "glm-5-2", org: null, config: null, metric: "pass_at_1", value: 0.4, ci_low: 0.35, ci_high: 0.45, rank: 2, extra: { mean_cost_usd: 1.2, mean_output_tokens: 20000, mean_agent_steps: 60 } }),
  ],
});

describe("DeepSweChart", () => {
  it("shows each model's best effort until every effort level is asked for", () => {
    render(<DeepSweChart site={deepswe} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "모든 추론 강도" }));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(4);
    expect(screen.getByText("70.0")).toBeInTheDocument();
    expect(screen.getByText("±3.0")).toBeInTheDocument();
  });

  it("switches the x axis", () => {
    render(<DeepSweChart site={deepswe} />);
    const toggle = within(screen.getByRole("group", { name: "가로축" })).getByRole("button", { name: "출력 토큰" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
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
    render(<ArtificialAnalysisCharts site={aa} />);
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
    expect(within(screen.getByRole("list", { name: "새로 등장한 모델" })).getByText(/gpt-5\.5/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Artificial Analysis" })).getByText("키 미설정")).toBeInTheDocument();
  });

  it("gives every card its source link and update time", () => {
    render(<ModelsTab summary={summary} sites={{ deepswe, livebench }} note="" />);
    const card = screen.getByRole("region", { name: "LiveBench" });
    expect(within(card).getByRole("link", { name: /원본/ })).toHaveAttribute("href", "https://livebench.ai/");
    expect(within(card).getByText(/LiveBench \(Abacus\.AI\)/)).toBeInTheDocument();
  });
});
