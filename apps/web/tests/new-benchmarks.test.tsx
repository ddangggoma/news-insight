import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { BenchmarksSection } from "@/components/reader/benchmarks/benchmarks-section";
import { ForecastBenchTable } from "@/components/reader/benchmarks/forecastbench";
import { SealCard } from "@/components/reader/benchmarks/seal";
import { SimpleBenchTable } from "@/components/reader/benchmarks/simplebench";
import { ValsCard } from "@/components/reader/benchmarks/vals";
import { VendingBenchCard } from "@/components/reader/benchmarks/vending-bench";
import { type BenchmarkRow, type BenchmarkSite, newModels } from "@/lib/benchmark-types";
import { forecastBenchView, forecastCell, sealView, simpleBenchView, valsCost, valsDuration, valsTokens, valsView, vendingBalance, vendingView } from "@/lib/benchmark-view";

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
  metric: "score",
  value: 0,
  ci_low: null,
  ci_high: null,
  extra: {},
  rank: null,
  change: null,
  change_by: 0,
  ...over,
});

const site = (over: Partial<BenchmarkSite>): BenchmarkSite => ({
  site: "seal",
  title: "Scale SEAL",
  source_url: "https://labs.scale.com/leaderboard",
  license: "라이선스 명시 없음",
  attribution: "SEAL Leaderboards (Scale AI)",
  release: "2026-11-11",
  fetched_at: "2026-11-13T03:31:00Z",
  stale: false,
  boards: ["main"],
  rows: [],
  ...over,
});

const cells = (table: HTMLElement) =>
  within(table)
    .getAllByRole("row")
    .slice(1)
    .map((tr) => [...tr.querySelectorAll("th, td")].map((cell) => cell.textContent ?? ""));

// ---- Scale SEAL: rows as the collector stores them (labs.scale.com, 2026-11-13) ----------

const sealRow = (board: string, order: number, title: string, model: string, rank: number, score: number, half: number, org: string, more: Record<string, unknown> = {}) =>
  row({ board, model, org, value: score, ci_low: score - half, ci_high: score + half, extra: { default_rank: rank, entry: model, label: model, board_title: title, board_order: order, board_id: board.split(":")[0], ci_half: half, ...more } });

const seal = site({
  // the API lists boards alphabetically; the card keeps the collector's order
  boards: ["hle-diamond", "swe_bench_pro_public_v2:full", "swe_bench_pro_public_v2:hard"],
  updated: { "hle-diamond": "2026-11-11", "swe_bench_pro_public_v2:hard": "2026-11-06", "swe_bench_pro_public_v2:full": "2026-11-06" },
  rows: [
    sealRow("swe_bench_pro_public_v2:full", 2, "SWE-Bench Pro V2 Full", "Fable 5.1 (Claude Code) high", 2, 99.1, 0.5, "anthropic"),
    sealRow("swe_bench_pro_public_v2:full", 2, "SWE-Bench Pro V2 Full", "Gemini 4 Argon (mini-swe-agent) high", 2, 99.22, 0.45, "openai"),
    sealRow("swe_bench_pro_public_v2:full", 2, "SWE-Bench Pro V2 Full", "Opus 5 (Claude Code) xhigh", 1, 99.4, 0.4, "anthropic"),
    sealRow("swe_bench_pro_public_v2:hard", 1, "SWE-Bench Pro V2 HARD", "Opus 5 (Claude Code) xhigh", 1, 98, 0, "anthropic"),
    sealRow("hle-diamond", 0, "Humanity's Last Exam (Diamond)", "gpt-6-astra", 2, 60.6, 3, "openai", { created: "2026-09-09" }),
    sealRow("hle-diamond", 0, "Humanity's Last Exam (Diamond)", "claude-fable-5-2", 1, 72.4, 2.68, "anthropic", { is_new: true, created: "2026-11-11" }),
    row({ board: "hle-diamond", model: "retired-model", org: "thinkingmachines", value: 11.2, extra: { board_title: "Humanity's Last Exam (Diamond)", board_order: 0, board_id: "hle-diamond", deprecated: true } }),
  ],
});

describe("SealCard", () => {
  it("opens on the first mirrored board with the site's Rank (UB), score and interval", () => {
    render(<SealCard boards={sealView(seal)} />);
    const picker = screen.getByRole("group", { name: "SEAL 벤치마크" });
    expect(within(picker).getAllByRole("button").map((b) => b.textContent)).toEqual(["Humanity's Last Exam (Diamond)", "SWE-Bench Pro V2 HARD", "SWE-Bench Pro V2 Full"]);
    const table = screen.getByRole("table", { name: "Scale SEAL Humanity's Last Exam (Diamond) 순위표" });
    const rows = cells(table);
    expect(rows.map((r) => r.slice(0, 3))).toEqual([
      ["1", "claude-fable-5-2NEW", "72.40 ± 2.68"],
      ["2", "gpt-6-astra", "60.60 ± 3.00"],
      ["—", "retired-model", "11.20"],
    ]);
    expect(rows[0][3]).toBe("Anthropic");
    expect(rows[2][3]).toBe("thinkingmachines"); // a maker without a colour reads as the site sends it
    expect(rows[0][4]).toBe("2026-11-11");
    expect(screen.getByRole("link", { name: "labs.scale.com에서 보기" })).toHaveAttribute("href", "https://labs.scale.com/leaderboard/hle-diamond");
  });

  it("switches boards; ranks the site shares stay shared", () => {
    render(<SealCard boards={sealView(seal)} />);
    fireEvent.click(screen.getByRole("button", { name: "SWE-Bench Pro V2 Full" }));
    const rows = cells(screen.getByRole("table", { name: "Scale SEAL SWE-Bench Pro V2 Full 순위표" }));
    expect(rows.map((r) => [r[0], r[1], r[2]])).toEqual([
      ["1", "Opus 5 (Claude Code) xhigh", "99.40 ± 0.40"],
      ["2", "Gemini 4 Argon (mini-swe-agent) high", "99.22 ± 0.45"],
      ["2", "Fable 5.1 (Claude Code) high", "99.10 ± 0.50"],
    ]);
    expect(screen.getByRole("link", { name: "labs.scale.com에서 보기" })).toHaveAttribute("href", "https://labs.scale.com/leaderboard/swe_bench_pro_public_v2");
  });
});

// ---- Vals Index ------------------------------------------------------------------------

const valsRow = (rank: number, model: string, org: string, accuracy: number, cost: number | null, tokens: number, latency: number, more: Record<string, unknown> = {}) =>
  row({ board: "vals_index", model, org, metric: "accuracy", value: accuracy, rank, extra: { default_rank: rank, entry: model, label: model, stderr: 0.956, cost_per_test: cost ?? undefined, tokens_per_test: tokens, latency, ...more } });

const vals = site({
  site: "vals",
  title: "Vals Index",
  license: "CC BY 4.0",
  boards: ["vals_index"],
  updated: { vals_index: "2026-11-11" },
  rows: [
    valsRow(1, "Claude Fable 5.2", "Anthropic", 71.309, 17.939202, 31311557.8, 2621.822),
    valsRow(2, "Claude Sonnet 5.5", "Anthropic", 70.854, 16.183857, 78585324.5, 5158.766),
    valsRow(3, "Gemini 4 Carbon", "Google", 70.45, 10.508065, 18285886, 2864.864),
    valsRow(4, "Gemini 4 Hydrogen", "Google", 68.492, 9.838059, 41192400.6, 1924.728),
    valsRow(5, "Kimi K3.1 Pro", "Moonshot AI", 62.52, 6.440192, 20139657.7, 3816.452, { open_weights: true }),
    valsRow(6, "Beam 1.0", "Reflection", 43.424, null, 5954438.2, 446.562),
  ],
});

describe("ValsCard", () => {
  it("prints the table as vals.ai does", () => {
    render(<ValsCard rows={valsView(vals)} updated="2026-11-11" />);
    const rows = cells(screen.getByRole("table", { name: "Vals Index 순위표" }));
    expect(rows.map((r) => [r[0], r[2], r[3], r[4], r[5]])).toEqual([
      ["1", "71.31%", "$17.94", "31.31m", "43m42s"],
      ["2", "70.85%", "$16.18", "78.59m", "1h26m"],
      ["3", "70.45%", "$10.51", "18.29m", "47m45s"],
      ["4", "68.49%", "$9.84", "41.19m", "32m05s"],
      ["5", "62.52%", "$6.44", "20.14m", "1h04m"],
      ["6", "43.42%", "-", "5.95m", "7m27s"],
    ]);
    expect(rows[4][1]).toContain("오픈 웨이트");
    expect(rows[0][1]).not.toContain("오픈 웨이트");
  });

  it("opens the ranking on the best model of each lab, as the site does", () => {
    const view = valsView(vals);
    expect(view.filter((r) => r.labBest).map((r) => r.model)).toEqual(["Claude Fable 5.2", "Gemini 4 Carbon", "Kimi K3.1 Pro", "Beam 1.0"]);
    render(<ValsCard rows={view} updated="2026-11-11" />);
    const toggle = screen.getByRole("group", { name: "순위 막대에 넣을 모델" });
    expect(within(toggle).getByRole("button", { name: "개발사별 최고 모델" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("개발사별 최고 모델 4개")).toBeInTheDocument();
    fireEvent.click(within(toggle).getByRole("button", { name: "모든 모델" }));
    expect(screen.getByText("전체 모델 6개")).toBeInTheDocument();
    expect(screen.getByText("정확도 대 테스트당 비용 (로그 눈금)")).toBeInTheDocument();
  });

  it("formats numbers the way vals.ai's table does", () => {
    expect(valsTokens(31311557.8)).toBe("31.31m");
    expect(valsDuration(2621.822)).toBe("43m42s");
    expect(valsDuration(5158.766)).toBe("1h26m");
    expect(valsDuration(1924.728)).toBe("32m05s");
    expect(valsCost(0.15305)).toBe("$0.15");
    expect([valsCost(null), valsTokens(null), valsDuration(null)]).toEqual(["-", "-", "-"]);
  });
});

// ---- Vending-Bench 2 -------------------------------------------------------------------

const vendingRow = (rank: number, name: string, model: string, org: string, value: number) =>
  row({ model, org, metric: "money_balance", value, rank, extra: { default_rank: rank, entry: model, label: name, release_date: "2026-10-28" } });

const vending = site({
  site: "vending_bench",
  title: "Vending-Bench 2",
  license: "CC BY 4.0 (Epoch AI 배포본)",
  updated: { main: "2026-10-28" },
  rows: [
    vendingRow(1, "Gemini 4 Carbon", "Gemini 4 Carbon (unknown)", "Google DeepMind", 16484.20666666667),
    vendingRow(2, "GPT-6 Astra", "GPT-6 Astra (unknown thinking)", "OpenAI", 15514.701666666668),
    ...Array.from({ length: 9 }, (_, i) => vendingRow(i + 3, `Model ${i + 3}`, `model-${i + 3}`, "Lab", 9000 - i * 500)),
    vendingRow(12, "MiniMax-M2.5", "MiniMax-M2.5", "MiniMax", -23.15999999999999),
  ],
});

describe("VendingBenchCard", () => {
  it("lists ten rows with Andon's names and balances, then the rest on request", () => {
    render(<VendingBenchCard rows={vendingView(vending)} updated="2026-10-28" />);
    const table = screen.getByRole("table", { name: "Vending-Bench 2 순위표" });
    let rows = cells(table);
    expect(rows).toHaveLength(10);
    expect(rows.slice(0, 2).map((r) => [r[0], r[1], r[2]])).toEqual([
      ["1", "Gemini 4 CarbonGoogle DeepMind", "$16,484.21"],
      ["2", "GPT-6 AstraOpenAI", "$15,514.70"],
    ]);
    // the model as Epoch names it stays on the row as its tooltip
    expect(within(table).getByText("Gemini 4 Carbon")).toHaveAttribute("title", "Gemini 4 Carbon (unknown)");
    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));
    rows = cells(table);
    expect(rows).toHaveLength(12);
    expect(rows[11].slice(0, 3)).toEqual(["12", "MiniMax-M2.5MiniMax", "-$23.16"]);
    expect(screen.getByRole("button", { name: "상위 10개만 보기" })).toBeInTheDocument();
  });

  it("writes a balance as the site does", () => {
    expect(vendingBalance(16484.20666666667)).toBe("$16,484.21");
    expect(vendingBalance(0.544)).toBe("$0.54");
    expect(vendingBalance(-31.184)).toBe("-$31.18");
  });
});

// ---- SimpleBench -----------------------------------------------------------------------

const simpleRow = (position: number, label: string, model: string, score: number, org: string | null, added: string | null) =>
  row({
    board: "mcq",
    model,
    org,
    value: score,
    rank: label === "-" ? null : Number.parseInt(label, 10),
    extra: { position, rank_label: label, entry: model, label: model, ...(label === "-" ? { human: true } : { default_rank: Number.parseInt(label, 10) }), ...(added ? { date_added: added } : {}) },
  });

const simplebench = site({
  site: "simplebench",
  title: "SimpleBench",
  license: "명시 없음",
  boards: ["mcq"],
  updated: { mcq: "2026-11-10" },
  rows: [
    // out of order, as the API sorts unranked rows last
    simpleRow(2, "1st", "Claude Fable 5.2", 94.9, "Anthropic", "2026-11-10"),
    simpleRow(3, "2nd", "Gemini 4 Carbon", 92.6, "Google", "2026-11-10"),
    simpleRow(5, "3rd", "GPT-6 Astra", 83.6, "OpenAI", "2026-09-07"),
    simpleRow(6, "4th", "GPT-3.5 Turbo", 8.0, "OpenAI", null),
    simpleRow(1, "-", "Highest Human Score*", 95.4, null, null),
    simpleRow(4, "-", "Human Baseline*", 83.7, null, null),
  ],
});

describe("SimpleBenchTable", () => {
  const view = simpleBenchView(simplebench, new Date("2026-11-13T00:00:00Z"));

  it("keeps the site's row order, rank labels and the human rows in place", () => {
    render(<SimpleBenchTable rows={view} updated="2026-11-10" />);
    const rows = cells(screen.getByRole("table", { name: "SimpleBench 순위표" }));
    expect(rows.map((r) => [r[0], r[1], r[2], r[3]])).toEqual([
      ["-", "Highest Human Score*사람 기준선", "95.4%", ""],
      ["1stNEW", "Claude Fable 5.2", "94.9%", "Anthropic"],
      ["2ndNEW", "Gemini 4 Carbon", "92.6%", "Google"],
      ["-", "Human Baseline*사람 기준선", "83.7%", ""],
      ["3rd", "GPT-6 Astra", "83.6%", "OpenAI"],
      ["4th", "GPT-3.5 Turbo", "8.0%", "OpenAI"],
    ]);
    expect(screen.getByText("4개 모델")).toBeInTheDocument();
  });

  it("tags a row NEW for two weeks after it was added, as the site does", () => {
    const later = simpleBenchView(simplebench, new Date("2026-11-25T00:00:00Z"));
    expect(view.filter((r) => r.isNew).map((r) => r.model)).toEqual(["Claude Fable 5.2", "Gemini 4 Carbon"]);
    expect(later.filter((r) => r.isNew)).toEqual([]);
  });
});

// ---- ForecastBench ---------------------------------------------------------------------

const forecastRow = (rank: number, team: string, model: string, overall: number, more: Record<string, unknown> = {}) => {
  const anonymous = team.toLowerCase().startsWith("anonymous");
  return row({
    board: "tournament",
    model,
    org: team,
    metric: "overall",
    value: overall,
    ci_low: overall - 1.2,
    ci_high: overall + 1.3,
    extra: { site_rank: rank, ...(anonymous ? { anonymous: true } : { default_rank: rank }), entry: `${team}/${model}`, label: model, team, dataset: 65.1, n_dataset: 1723, dataset_ci: "[63.8, 66.5]", market: 72.5, n_market: 140, market_ci: "[70.4, 75.0]", n: 1863, supers_beat: "No", beats_public: "Yes", ...more },
  });
};

const forecastbench = site({
  site: "forecastbench",
  title: "ForecastBench",
  license: "CC BY-SA 4.0",
  boards: ["tournament"],
  updated: { tournament: "2026-11-11" },
  rows: [
    forecastRow(3, "Google DeepMind", "fire hedgehog", 68.6),
    forecastRow(4, "NeuroFusion", "ensemble 1", 68.5),
    forecastRow(8, "ForecastBench", "Superforecaster median forecast", 68.2, { supers_beat: "—" }),
    forecastRow(1, "Anonymous 24", "model-4", 69.5),
    forecastRow(2, "Anonymous 24", "model-5", 68.8),
  ],
});

describe("ForecastBenchTable", () => {
  it("opens with anonymous teams hidden, ranks counted over every row", () => {
    render(<ForecastBenchTable rows={forecastBenchView(forecastbench)} updated="2026-11-11" />);
    const table = screen.getByRole("table", { name: "ForecastBench 토너먼트 순위표" });
    const header = within(table)
      .getAllByRole("columnheader")
      .map((th) => th.textContent);
    expect(header).toEqual(["순위", "모델", "개발사", "데이터셋 (N)", "데이터셋 95% CI", "시장 (N)", "시장 95% CI", "종합 (N)", "종합 95% CI", "슈퍼포캐스터 > 모델?", "모델 > 일반인?"]);
    const rows = cells(table);
    expect(rows.map((r) => [r[0], r[1], r[2], r[3], r[5], r[7], r[8], r[9]])).toEqual([
      ["3", "fire hedgehog", "Google DeepMind", "65.1 (1,723)", "72.5 (140)", "68.6 (1,863)", "[67.4, 69.9]", "No"],
      ["4", "ensemble 1", "NeuroFusion", "65.1 (1,723)", "72.5 (140)", "68.5 (1,863)", "[67.3, 69.8]", "No"],
      ["8", "Superforecaster median forecast", "ForecastBench", "65.1 (1,723)", "72.5 (140)", "68.2 (1,863)", "[67.0, 69.5]", "—"],
    ]);
  });

  it("shows the anonymous teams when asked", () => {
    render(<ForecastBenchTable rows={forecastBenchView(forecastbench)} updated="2026-11-11" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "익명 팀 보기 (2개 행)" }));
    const rows = cells(screen.getByRole("table", { name: "ForecastBench 토너먼트 순위표" }));
    expect(rows.map((r) => [r[0], r[1]])).toEqual([
      ["1", "model-4"],
      ["2", "model-5"],
      ["3", "fire hedgehog"],
      ["4", "ensemble 1"],
      ["8", "Superforecaster median forecast"],
    ]);
  });

  it("writes a score with its question count", () => {
    expect(forecastCell(65.1, 723)).toBe("65.1 (723)");
    expect(forecastCell(68, 12863)).toBe("68.0 (12,863)");
    expect(forecastCell(null, 3)).toBe("—");
  });
});

// ---- in the 벤치마크 tab ----------------------------------------------------------------

describe("BenchmarksSection with the sites added 2026-11-13", () => {
  it("renders each new card when picked, with source, licence and attribution", () => {
    const picked = { seal, vals, vending_bench: vending, simplebench, forecastbench } as const;
    for (const key of ["seal", "vals", "vending_bench", "simplebench", "forecastbench"] as const) {
      const { unmount } = render(<BenchmarksSection summary={null} site={key} full={picked[key]} note="" />);
      const card = screen.getByRole("region", { name: picked[key].title });
      expect(within(card).getByRole("link", { name: /원본/ })).toHaveAttribute("href", picked[key].source_url);
      expect(within(card).getByText(`라이선스: ${picked[key].license}`)).toBeInTheDocument();
      expect(within(card).getByText(`출처: ${picked[key].attribution}`)).toBeInTheDocument();
      expect(within(card).getAllByRole("table").length).toBe(1);
      unmount();
    }
  });
});

describe("arrivals of the sites added 2026-11-13", () => {
  it("tells SEAL's named boards, Vals, Vending-Bench and SimpleBench, never ForecastBench", () => {
    const fresh = (board: string, label: string) => row({ board, model: "x", rank: 1, change: "new", extra: { label } });
    const arrivals = newModels([
      site({ rows: [fresh("hle-diamond", "claude-fable-5-2"), fresh("hss", "Gemini 4 Carbon (high)"), fresh("swe_bench_pro_public_v2:hard", "Opus 5 (Claude Code) xhigh")] }),
      site({ site: "vals", title: "Vals Index", rows: [fresh("vals_index", "Claude Fable 5.2")] }),
      site({ site: "vending_bench", title: "Vending-Bench 2", rows: [fresh("main", "Gemini 4 Carbon")] }),
      site({ site: "simplebench", title: "SimpleBench", rows: [fresh("mcq", "Claude Fable 5.2")] }),
      site({ site: "forecastbench", title: "ForecastBench", rows: [fresh("tournament", "fire hedgehog")] }),
    ]);
    expect(arrivals.map((a) => `${a.site}:${a.board}:${a.model}`)).toEqual([
      "seal:hle-diamond:claude-fable-5-2",
      "seal:swe_bench_pro_public_v2:hard:Opus 5 (Claude Code) xhigh",
      "vals:vals_index:Claude Fable 5.2",
      "vending_bench:main:Gemini 4 Carbon",
      "simplebench:mcq:Claude Fable 5.2",
    ]);
  });
});
