import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { BenchmarksSection } from "@/components/reader/benchmarks/benchmarks-section";
import { EpochCard } from "@/components/reader/benchmarks/epoch";
import { OsWorldTable } from "@/components/reader/benchmarks/osworld";
import { Tau2Table, rankTau2 } from "@/components/reader/benchmarks/tau2";
import { TerminalBenchCard, bestByAgent } from "@/components/reader/benchmarks/terminal-bench";
import type { BenchmarkRow, BenchmarkSite } from "@/lib/benchmark-types";
import { epochScore, epochView, formatDurationMinutes, osPercent, osWorldView, tau2View, tbCost, tbTokens, terminalBenchView } from "@/lib/benchmark-view";

beforeAll(() => {
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
  metric: "accuracy",
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
  site: "terminal_bench",
  title: "Terminal-Bench",
  source_url: "https://www.tbench.ai/",
  license: "Apache-2.0",
  attribution: "Terminal-Bench",
  release: "2026-10-23",
  fetched_at: "2026-11-08T03:31:00Z",
  stale: false,
  boards: ["2.1", "3.0", "4.0"],
  updated: { "4.0": "2026-10-23", "3.0": "2026-09-03", "2.1": "2026-09-03" },
  rows: [],
  ...over,
});

// tbench.ai 4.0 as recorded 2026-11-08 (its first rows): rank (default view), API rank
function tb(board: string, agent: string, model: string, effort: string, accuracy: number, rank: number | null, apiRank: number, cost = 1000): BenchmarkRow {
  return row({
    board,
    model,
    config: effort,
    org: agent === "Codex" ? "OpenAI" : "Anthropic",
    value: accuracy,
    ci_low: accuracy - 3,
    ci_high: accuracy + 3,
    rank,
    extra: { agent, rank: apiRank, ...(rank === null ? {} : { default_rank: rank }), total_cost_usd: cost, total_tokens: 8.03e9, date: "2026-09-22", row_id: `${board}-${model}-${effort}` },
  });
}

const terminalBench = site({
  rows: [
    tb("4.0", "Claude Code", "Opus 5.5", "max", 64.85, 1, 1, 4718.65),
    tb("4.0", "Claude Code", "Sonnet 5.5", "max", 61.82, 2, 2),
    tb("4.0", "Codex", "GPT-6 Astra", "max", 58.18, 3, 3),
    tb("4.0", "Codex", "GPT-6.1 Sol", "max", 58.18, 3, 3, 634.24),
    tb("4.0", "Codex", "GPT-6 Astra", "xhigh", 57.88, null, 5),
    tb("4.0", "Grok Build", "Grok 4.7", "xhigh", 37.58, 6, 21),
    tb("3.0", "Devin", "SWE-1.7 Lightning", "none", 18.65, 1, 8),
  ],
});

describe("TerminalBenchCard", () => {
  const view = terminalBenchView(terminalBench);

  it("opens on 4.0 with the site's best-effort rows and shared ranks", () => {
    expect(view.boards).toEqual(["4.0", "3.0"]);
    render(<TerminalBenchCard view={view} />);
    const table = screen.getByRole("table", { name: "Terminal-Bench 4.0 순위표" });
    const heads = within(table).getAllByRole("rowheader").map((h) => h.textContent);
    expect(heads).toEqual(["1", "2", "3", "3", "6"]);
    // tbench.ai's column order: rank, model, agent
    expect(within(table).getAllByRole("columnheader").slice(0, 3).map((h) => h.textContent?.replace(/[↑↓↕]/g, "").trim())).toEqual(["순위", "모델", "에이전트"]);
    expect(within(table).getByText("64.8% ± 3.0%")).toBeInTheDocument();
    expect(within(table).getByText("$4.7k")).toBeInTheDocument();
    expect(within(table).getByText("$0.6k")).toBeInTheDocument();
    expect(within(table).getAllByRole("img", { name: /^정확도 / })).toHaveLength(5);
  });

  it("summarises each agent's best score above the table", () => {
    render(<TerminalBenchCard view={view} />);
    const list = screen.getByRole("list", { name: "에이전트별 최고 점수" });
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector("span")?.textContent)).toEqual(["Claude Code", "Codex", "Grok Build"]);
    expect(bestByAgent(view.rows.filter((r) => r.board === "4.0")).map((r) => r.model)).toEqual(["Opus 5.5", "GPT-6 Astra", "Grok 4.7"]);
  });

  it("filters by agent with the chip row built from the data", () => {
    render(<TerminalBenchCard view={view} />);
    const chips = screen.getByRole("group", { name: "에이전트별" });
    expect(within(chips).getAllByRole("button").map((b) => b.textContent)).toEqual(["전체", "Claude Code", "Codex", "Grok Build"]);
    fireEvent.click(within(chips).getByRole("button", { name: "Codex" }));
    expect(within(chips).getByRole("button", { name: "Codex" })).toHaveAttribute("aria-pressed", "true");
    const table = screen.getByRole("table", { name: "Terminal-Bench 4.0 순위표" });
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["3", "3"]);
    expect(within(table).getAllByText("Codex")).toHaveLength(2);
    fireEvent.click(within(chips).getByRole("button", { name: "전체" }));
    expect(within(screen.getByRole("table")).getAllByRole("rowheader")).toHaveLength(5);
  });

  it("switches boards and the site's all-efforts view", () => {
    render(<TerminalBenchCard view={view} />);
    fireEvent.click(screen.getByRole("button", { name: "모든 강도" }));
    // every effort, ranked as the board serves them
    expect(within(screen.getByRole("table")).getAllByRole("rowheader")).toHaveLength(6);
    fireEvent.click(screen.getByRole("button", { name: "TB 3.0" }));
    const table = screen.getByRole("table", { name: "Terminal-Bench 3.0 순위표" });
    expect(within(table).getByText("SWE-1.7 Lightning")).toBeInTheDocument();
  });

  it("prints tokens and cost as the site does", () => {
    expect(tbTokens(8034082467)).toBe("8.0B");
    expect(tbCost(634.24)).toBe("$0.6k");
    expect(tbCost(0)).toBe("—");
  });
});

const osworld = site({
  site: "osworld",
  title: "OSWorld 2.0",
  boards: ["main"],
  updated: { main: "2026-10-15" },
  rows: [
    row({ model: "Claude Opus 5", org: "Anthropic", config: "max", metric: "binary_accuracy", value: 44.33, extra: { default_rank: 1, partial_score: 77.67, tool_setting: "batch tool", step_budget: 500, release_version: "v2.1" } }),
    row({ model: "Claude Opus 4.7", org: "Anthropic", config: "max", metric: "binary_accuracy", value: 13.9, extra: { default_rank: 2, partial_score: 49.1, tool_setting: "standard", step_budget: 500, release_version: "v2026.06.24", cost_per_task: 35.8 } }),
    row({ model: "Sai w/ Claude Opus 5", org: "Simular", metric: "binary_accuracy", value: 41.67, extra: { tool_setting: "", step_budget: 500 } }),
  ],
});

describe("OsWorldTable", () => {
  it("shows the site's default table only, in its order and format", () => {
    const rows = osWorldView(osworld);
    expect(rows.map((r) => r.model)).toEqual(["Claude Opus 5", "Claude Opus 4.7"]);
    render(<OsWorldTable rows={rows} updated="2026-10-15" />);
    const table = screen.getByRole("table", { name: "OSWorld 2.0 순위표" });
    expect(within(table).getByText("44.33%")).toBeInTheDocument();
    expect(within(table).getByText("49.1%")).toBeInTheDocument();
    expect(within(table).getByText("$35.8")).toBeInTheDocument();
    expect(within(table).getByText("Batch tool")).toBeInTheDocument();
    expect(screen.getByText(/2026년 10월 15일/)).toBeInTheDocument();
    expect(osPercent(20.6)).toBe("20.6%");
    expect(osPercent(44.33)).toBe("44.33%");
  });
});

function tau(board: string, model: string, passes: number[], rank: number | null, extra: Record<string, unknown> = {}): BenchmarkRow {
  return row({
    board,
    model,
    metric: "pass_1",
    value: passes[0],
    extra: { pass_2: passes[1], pass_3: passes[2], pass_4: passes[3], submitting_org: "Sierra", verified: true, submission_type: "standard", entry: `${model}-${board}`, ...(rank === null ? {} : { default_rank: rank }), ...extra },
  });
}

const tau2 = site({
  site: "tau2",
  title: "τ²-bench",
  boards: ["airline", "banking_knowledge", "overall", "voice"],
  updated: { overall: "2026-03-02", banking_knowledge: "2026-08-04", voice: "2026-10-27" },
  rows: [
    tau("overall", "Claude Opus 4.5", [85.31, 79.0, 75.0, 72.0], 1),
    tau("overall", "GPT-5.2", [84.8, 80.0, 77.0, 74.5], 2),
    tau("overall", "Custom agent", [90, 85, 80, 78], null, { submission_type: "custom", submitting_org: "Distyl AI" }),
    tau("airline", "Claude Opus 4.5", [84.0, 80, 76, 72], 1),
    tau("banking_knowledge", "Claude Opus 5", [48.71, 39.2, 34.5, 31.96], 1, { retrieval_config: "alltools" }),
    tau("banking_knowledge", "Claude Opus 4.5", [24.74, 18, 15, 13], 2, { verified: false }),
    tau("voice", "Pine Voice 1.0", [87.33, 0, 0, 0], 1, { voice_provider: "Pine AI", submitting_org: "PineAI" }),
  ],
});

describe("Tau2Table", () => {
  const view = tau2View(tau2);

  it("opens on τ³-Banking as the site does; τ²-bench overall is pass^1, standard submissions only", () => {
    expect(view.boards).toEqual(["overall", "airline", "banking_knowledge", "voice"]);
    render(<Tau2Table view={view} />);
    expect(screen.getByRole("table", { name: /τ³-Banking/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "τ²-bench" }));
    const table = screen.getByRole("table", { name: /τ²-bench 전체 순위표/ });
    expect(within(table).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["1Claude Opus 4.5", "2GPT-5.2"]);
    expect(within(table).getByText("85.3%")).toBeInTheDocument();
  });

  it("re-ranks by pass^k and switches track", () => {
    render(<Tau2Table view={view} />);
    fireEvent.click(screen.getByRole("button", { name: "τ²-bench" }));
    fireEvent.click(screen.getByRole("button", { name: "pass^4" }));
    expect(within(screen.getByRole("table")).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["1GPT-5.2", "2Claude Opus 4.5"]);
    fireEvent.click(screen.getByRole("button", { name: "τ³-Banking" }));
    const table = screen.getByRole("table", { name: /τ³-Banking/ });
    expect(within(table).getByText("alltools")).toBeInTheDocument();
    // the site's warning mark on an unverified submission, and who submitted each row
    expect(within(table).getByRole("img", { name: "미검증 제출" })).toBeInTheDocument();
    expect(within(table).getAllByText("Sierra")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "τ³-Voice (영어)" }));
    expect(screen.queryByRole("button", { name: "pass^4" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Pine AI")).toBeInTheDocument();
  });

  it("ranks a missing pass^k last", () => {
    const rows = view.rows.filter((r) => r.board === "overall").map((r, i) => (i === 0 ? { ...r, passes: [r.passes[0], null, null, null] } : r));
    expect(rankTau2(rows, 4).map((r) => r.model)).toEqual(["GPT-5.2", "Claude Opus 4.5"]);
  });
});

function ep(board: string, model: string, value: number, rank: number, unit: string, extra: Record<string, unknown> = {}, ci?: [number, number]): BenchmarkRow {
  return row({ board, model, metric: "score", value, ci_low: ci?.[0] ?? null, ci_high: ci?.[1] ?? null, extra: { default_rank: rank, unit, ...extra } });
}

const epoch = site({
  site: "epoch",
  title: "Epoch AI",
  boards: ["eci", "gpqa_diamond", "metr_time_horizons"],
  updated: { eci: "2026-10-29", gpqa_diamond: "2026-11-06", metr_time_horizons: "2026-04-07" },
  rows: [
    ep("eci", "GPT-6 Astra", 169.07, 1, "index", {}, [166.16, 172.28]),
    ep("eci", "Claude Opus 5.5", 168.36, 2, "index", {}, [165.54, 171.51]),
    ep("gpqa_diamond", "Gemini 4 Argon (high)", 0.964, 1, "percent"),
    ep("metr_time_horizons", "Claude Mythos Preview (Early)", 1044.78, 1, "minutes", { source: "https://metr.org/blog/x" }),
  ],
});

describe("EpochCard", () => {
  const boards = epochView(epoch);

  it("opens on the ECI with its top-20 chart and switches boards", () => {
    expect(boards.map((b) => b.key)).toEqual(["eci", "gpqa_diamond", "metr_time_horizons"]);
    render(<EpochCard boards={boards} />);
    expect(screen.getByText("ECI 상위 2개 모델")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /ECI/ });
    expect(within(table).getByText("169")).toBeInTheDocument();
    expect(within(table).getAllByText("[166–172]")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "METR 시간 지평" }));
    const metr = screen.getByRole("table", { name: /METR/ });
    expect(within(metr).getByText("17 hr 25 min")).toBeInTheDocument();
    expect(within(metr).getByRole("link", { name: "metr.org" })).toHaveAttribute("href", "https://metr.org/blog/x");
    expect(screen.queryByText(/ECI 상위/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "GPQA Diamond" }));
    expect(within(screen.getByRole("table")).getByText("96.4%")).toBeInTheDocument();
  });

  it("prints scores as epoch.ai does", () => {
    expect(formatDurationMinutes(1044.78)).toBe("17 hr 25 min");
    expect(formatDurationMinutes(59.3)).toBe("59 min 18 sec");
    expect(formatDurationMinutes(120)).toBe("2 hr");
    expect(epochScore(0.9577, "percent")).toBe("95.8%");
    expect(epochScore(168.36, "index")).toBe("168");
  });
});

describe("BenchmarksSection with the agent benchmarks", () => {
  it("renders every new card, with source, licence and attribution", () => {
    render(<BenchmarksSection summary={null} sites={{ terminal_bench: terminalBench, osworld, tau2, epoch }} note="" />);
    for (const name of ["Terminal-Bench", "OSWorld 2.0", "τ²-bench", "Epoch AI"]) {
      const card = screen.getByRole("region", { name });
      expect(within(card).getByRole("link", { name: /원본/ })).toBeInTheDocument();
      expect(within(card).getByText("Apache-2.0")).toBeInTheDocument();
    }
    const nav = screen.getByRole("navigation", { name: "벤치마크 사이트" });
    expect(within(nav).getByRole("link", { name: "AI 에이전트 벤치마크" })).toHaveAttribute("href", "#bench-group-agents");
    expect(within(nav).getByRole("link", { name: /Terminal-Bench/ })).toHaveAttribute("href", "#bench-terminal_bench");
  });

  it("says when a site was never collected and when it is stale", () => {
    render(<BenchmarksSection summary={[{ ...terminalBench, stale: true, rows: [] }]} sites={{ terminal_bench: { ...terminalBench, stale: true } }} note="" />);
    expect(within(screen.getByRole("region", { name: "Terminal-Bench" })).getByText("갱신 지연")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "OSWorld 2.0" })).getByText("아직 수집된 순위가 없습니다.")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Epoch AI" })).getByText("아직 수집된 순위가 없습니다.")).toBeInTheDocument();
  });
});

describe("arrivals of the newer sites", () => {
  it("tells only Terminal-Bench 4.0 and Epoch's ECI, by label", async () => {
    const { newModels } = await import("@/lib/benchmark-types");
    const fresh = (board: string, label: string) => row({ board, model: "x", rank: 1, change: "new", extra: { label } });
    const arrivals = newModels([
      site({ rows: [fresh("4.0", "Claude Code · Opus 5.5"), fresh("3.0", "Codex · GPT-6 Sol")] }),
      site({ site: "epoch", title: "Epoch AI", rows: [fresh("eci", "GPT-6 Astra"), fresh("hle", "Muse Spark")] }),
      site({ site: "osworld", title: "OSWorld 2.0", rows: [fresh("main", "Claude Opus 5 (max)")] }),
    ]);
    expect(arrivals.map((a) => `${a.site}:${a.board}:${a.model}`)).toEqual(["terminal_bench:4.0:Claude Code · Opus 5.5", "epoch:eci:GPT-6 Astra"]);
  });
});
