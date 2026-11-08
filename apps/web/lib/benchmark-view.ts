/**
 * Server-side projections of the stored leaderboard rows into what each card draws. The page
 * runs these before handing props to the client components, so the browser gets one small
 * record per model or point instead of every stored row with its `extra` (plan 18, R21/R24).
 */
import { family } from "@/components/reader/benchmarks/deepswe-plot";
import { type ProviderKey, providerKey } from "@/components/reader/benchmarks/provider-colors";
import {
  AA_METRICS,
  BENCHMARK_SITES,
  type BenchmarkChange,
  type BenchmarkRow,
  type BenchmarkSite,
  type BenchmarkSiteKey,
  LIVEBENCH_CATEGORIES,
  LMARENA_BOARD_LABEL,
  TAU2_BOARDS,
  colourOrg,
  extraNumber,
  extraString,
  newestBoardFirst,
} from "@/lib/benchmark-types";

/** A site without its rows: what a card's header and footer show. */
export type SiteMeta = Omit<BenchmarkSite, "rows">;

export function siteMeta({ rows: _rows, ...meta }: BenchmarkSite): SiteMeta {
  return meta;
}

const provider = (org: string | null, model: string): ProviderKey => providerKey(colourOrg(org, model));

/** A few decimals are all any card prints; the API sends full floats. */
const round = (v: number, digits = 2) => Math.round(v * 10 ** digits) / 10 ** digits;
const r2 = (v: number) => round(v);
const r2n = (v: number | null, digits = 2) => (v === null ? null : round(v, digits));

// ---- DeepSWE -------------------------------------------------------------------------

export interface DsPoint {
  id: string;
  board: string;
  model: string;
  effort: string | null;
  /** The maker as DeepSWE tells it, by model name. */
  provider: ProviderKey;
  /** pass@1 in percent, and its 95% interval. */
  score: number;
  low: number | null;
  high: number | null;
  cost: number | null;
  tokens: number | null;
  steps: number | null;
  harness: string | null;
  /** The model's best configuration on the board (the ranked row). */
  best: boolean;
  /** The model is in the site's default set (the chart's and table's opening models). */
  shown: boolean;
  change: BenchmarkChange | null;
  changeBy: number;
}

export interface DeepSweView {
  /** Newest version first; the card opens on the first. */
  boards: string[];
  points: DsPoint[];
  /** Per board: tasks in the set and the day the site generated it, when known. */
  info: Record<string, { tasks: number | null; updated: string | null }>;
}

export function deepSweView(site: BenchmarkSite): DeepSweView {
  const pct = (v: number | null) => (v === null ? null : r2(v * 100));
  const points = site.rows
    .filter((row) => row.metric === "pass_at_1")
    .map(
      (row, index): DsPoint => ({
        id: `${row.board}|${row.model}|${row.config ?? ""}|${index}`,
        board: row.board,
        model: row.model,
        effort: row.config,
        provider: family(row.model),
        score: r2(row.value * 100),
        low: pct(row.ci_low),
        high: pct(row.ci_high),
        cost: r2n(extraNumber(row, "mean_cost_usd")),
        tokens: r2n(extraNumber(row, "mean_output_tokens")),
        steps: r2n(extraNumber(row, "mean_agent_steps")),
        harness: extraString(row, "harness"),
        best: row.rank !== null,
        shown: false,
        change: row.change,
        changeBy: row.change_by,
      }),
    );
  for (const board of new Set(points.map((p) => p.board))) {
    const onBoard = points.filter((p) => p.board === board);
    // the API ranks exactly the site's default models (their best configuration)
    const ranked = new Set(onBoard.filter((p) => p.best).map((p) => p.model));
    if (ranked.size > 0) {
      for (const p of onBoard) p.shown = ranked.has(p.model);
      continue;
    }
    // a board with no ranking at all: every model shown, each best configuration marked
    const best = new Map<string, DsPoint>();
    for (const p of onBoard) if ((best.get(p.model)?.score ?? -1) < p.score) best.set(p.model, p);
    for (const p of best.values()) p.best = true;
    for (const p of onBoard) p.shown = true;
  }
  const boards = newestBoardFirst(site.boards.filter((b) => points.some((p) => p.board === b)));
  // the rows carry each config's task count; each board's date is the site's own, else (an
  // older snapshot) the snapshot's release for the newest board
  const info: DeepSweView["info"] = {};
  for (const board of boards) {
    const counts = site.rows.filter((r) => r.board === board).map((r) => extraNumber(r, "n_tasks_in_set") ?? extraNumber(r, "n_tasks_attempted") ?? 0);
    const tasks = Math.max(0, ...counts);
    const updated = site.updated?.[board] ?? (board === boards[0] ? site.release || null : null);
    info[board] = { tasks: tasks || null, updated };
  }
  return { boards, points, info };
}

// ---- LiveBench -----------------------------------------------------------------------

type Category = (typeof LIVEBENCH_CATEGORIES)[number]["key"];

export interface LiveModel {
  /** The site's model key (row id). */
  model: string;
  /** The site's display name, else the key. */
  name: string;
  /** The site's own organisation; null when it does not say. */
  org: string | null;
  provider: ProviderKey;
  /** True only when the site marks the weights open. */
  open: boolean;
  overall: number | null;
  /** Null when the site leaves the model out of its default table (not in its model list, a
   * fine-tune, or a variant beaten by its base model). */
  rank: number | null;
  coverage: number | null;
  change: BenchmarkChange | null;
  changeBy: number;
  scores: Partial<Record<Category, number>>;
  parts: Partial<Record<Category, Record<string, number>>>;
  /** The site's "cost per successful task": (Σ cost ÷ Σ tasks) ÷ overall × 100. */
  costPerSuccess: number | null;
}

const CATEGORY_KEYS = new Set<string>(LIVEBENCH_CATEGORIES.map((c) => c.key));

/**
 * One record per model: categories, the API's (weighted) overall, the site's metadata, cost.
 * Ordered ranked first by rank, then the unranked by overall, best first — the table's
 * default order, which also breaks ties when it sorts.
 */
export function liveBenchModels(site: BenchmarkSite): LiveModel[] {
  const byModel = new Map<string, LiveModel & { cost: number; tasks: number }>();
  const entry = (row: BenchmarkRow) => {
    let found = byModel.get(row.model);
    if (!found) {
      found = {
        model: row.model,
        name: row.model,
        org: null,
        provider: "other",
        open: false,
        overall: null,
        rank: null,
        coverage: null,
        change: null,
        changeBy: 0,
        scores: {},
        parts: {},
        costPerSuccess: null,
        cost: 0,
        tasks: 0,
      };
      byModel.set(row.model, found);
    }
    // the site's metadata rides on the score rows and the derived overall row
    const display = extraString(row, "display_name");
    if (display) found.name = display;
    const org = extraString(row, "organization") ?? row.org;
    if (org) found.org = org;
    if (row.extra.open_weights === true) found.open = true;
    return found;
  };
  for (const row of site.rows) {
    const model = entry(row);
    if (row.metric === "overall") {
      model.overall = row.value;
      model.rank = row.rank;
      model.coverage = extraNumber(row, "coverage");
      model.change = row.change;
      model.changeBy = row.change_by;
    } else if (row.metric === "cost_per_success") {
      const tasks = extraNumber(row, "questions");
      if (tasks !== null && tasks > 0) {
        model.cost += row.value;
        model.tasks += tasks;
      }
    } else if (CATEGORY_KEYS.has(row.metric)) {
      const key = row.metric as Category;
      model.scores[key] = row.value;
      const parts = row.extra.parts;
      if (parts && typeof parts === "object") model.parts[key] = parts as Record<string, number>;
    }
  }
  const models = [...byModel.values()].map(({ cost, tasks, ...model }) => {
    if (model.overall === null) {
      const values = Object.values(model.scores);
      model.overall = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
    }
    model.provider = provider(model.org, model.model);
    model.costPerSuccess = tasks > 0 && model.overall ? round((cost / tasks / model.overall) * 100, 4) : null;
    if (model.overall !== null) model.overall = r2(model.overall);
    return model;
  });
  return models.sort((a, b) => {
    if (a.rank !== null && b.rank !== null) return a.rank - b.rank;
    if (a.rank !== null) return -1;
    if (b.rank !== null) return 1;
    return (b.overall ?? -Infinity) - (a.overall ?? -Infinity);
  });
}

// ---- LMArena -------------------------------------------------------------------------

export interface ArenaRow {
  /** The site's rank (ties share one). */
  rank: number | null;
  /** The site's name, effort level included ("… (High)"). */
  model: string;
  org: string | null;
  score: number;
  low: number | null;
  high: number | null;
  /** Votes; sessions on the agent board. */
  votes: number | null;
  license: string | null;
  /** Only on rows that moved (most do not; ~840 rows ride in the page). */
  change?: BenchmarkChange;
  changeBy?: number;
}

export interface ArenaBoard {
  key: string;
  published: string | null;
  rows: ArenaRow[];
}

/** Boards in the site's tab order: 텍스트, 웹개발, 비전, 검색, 에이전트 (then anything new). */
export type ArenaView = ArenaBoard[];

const ARENA_ORDER = Object.keys(LMARENA_BOARD_LABEL);

/**
 * The largest site (~840 rows): grouped by board, floats rounded, and nothing the client can
 * derive (colour, openness come from org and licence on the client).
 */
export function lmArenaView(site: BenchmarkSite): ArenaView {
  const boards = new Map<string, ArenaBoard>();
  for (const row of site.rows) {
    let board = boards.get(row.board);
    if (!board) {
      board = { key: row.board, published: null, rows: [] };
      boards.set(row.board, board);
    }
    const date = site.updated?.[row.board] ?? extraString(row, "leaderboard_publish_date");
    if (date && (board.published ?? "") < date) board.published = date;
    // the agent board is a 0-1 share: keep four decimals there
    const digits = row.board === "agent" ? 4 : 2;
    board.rows.push({
      rank: extraNumber(row, "rank") ?? row.rank,
      model: row.model,
      org: row.org,
      score: round(row.value, digits),
      low: r2n(row.ci_low, digits),
      high: r2n(row.ci_high, digits),
      votes: extraNumber(row, "vote_count") ?? extraNumber(row, "session_count"),
      license: extraString(row, "license"),
      ...(row.change && row.change !== "same" ? { change: row.change, changeBy: row.change_by } : {}),
    });
  }
  const order = (b: string) => (ARENA_ORDER.includes(b) ? ARENA_ORDER.indexOf(b) : ARENA_ORDER.length);
  return [...boards.values()].sort((a, b) => order(a.key) - order(b.key) || site.boards.indexOf(a.key) - site.boards.indexOf(b.key));
}

// ---- Artificial Analysis -------------------------------------------------------------

export interface AaModel {
  model: string;
  org: string | null;
  provider: ProviderKey;
  intelligence: number | null;
  price: number | null;
  speed: number | null;
}

/** One record per model with the three plotted numbers (the API stores ~60 metrics each). */
export function aaModels(site: BenchmarkSite): AaModel[] {
  const byModel = new Map<string, AaModel>();
  for (const row of site.rows) {
    const entry = byModel.get(row.model) ?? { model: row.model, org: row.org, provider: provider(row.org, row.model), intelligence: null, price: null, speed: null };
    if (row.metric === AA_METRICS.intelligence) entry.intelligence = row.value;
    else if (row.metric === AA_METRICS.price) entry.price = row.value;
    else if (row.metric === AA_METRICS.speed) entry.speed = row.value;
    else continue;
    byModel.set(row.model, entry);
  }
  return [...byModel.values()];
}

// ---- the newer sites: their collectors store the site's default view -------------------

/** The place in the site's default view, ties shared as the site prints them; null: not shown. */
const defaultRank = (row: BenchmarkRow) => extraNumber(row, "default_rank");
const byDefaultRank = (a: { rank: number | null }, b: { rank: number | null }) => (a.rank ?? Infinity) - (b.rank ?? Infinity);

// ---- Terminal-Bench ------------------------------------------------------------------

export interface TbRow {
  id: string;
  board: string;
  /** Rank in the site's default table (best effort per model and agent); null when that table
   * leaves the row out (a lower effort of the same model and agent). */
  rank: number | null;
  /** Rank among every effort (the site's "all efforts" view). */
  allRank: number | null;
  agent: string;
  model: string;
  effort: string | null;
  provider: ProviderKey;
  /** Resolution rate in percent and its 95% interval. */
  accuracy: number;
  low: number | null;
  high: number | null;
  date: string | null;
  tokens: number | null;
  cost: number | null;
  change: BenchmarkChange | null;
  changeBy: number;
}

export interface TbView {
  /** The site's order: 4.0 (its default), 3.0, 2.1. */
  boards: string[];
  updated: Record<string, string>;
  rows: TbRow[];
}

export function terminalBenchView(site: BenchmarkSite): TbView {
  const rows = site.rows
    .filter((row) => row.metric === "accuracy")
    .map(
      (row, index): TbRow => ({
        id: `${row.board}|${extraString(row, "row_id") ?? index}`,
        board: row.board,
        rank: defaultRank(row),
        allRank: extraNumber(row, "rank"),
        agent: extraString(row, "agent") ?? "—",
        model: row.model,
        effort: row.config,
        provider: provider(row.org, row.model),
        accuracy: r2(row.value),
        low: r2n(row.ci_low),
        high: r2n(row.ci_high),
        date: extraString(row, "date"),
        tokens: extraNumber(row, "total_tokens"),
        cost: r2n(extraNumber(row, "total_cost_usd")),
        change: row.change,
        changeBy: row.change_by,
      }),
    )
    .sort((a, b) => byDefaultRank({ rank: a.allRank }, { rank: b.allRank }));
  // the site's order: newest version first (4.0, its default, then 3.0 and 2.1)
  const boards = newestBoardFirst([...new Set(rows.map((r) => r.board))]);
  return { boards, updated: site.updated ?? {}, rows };
}

// ---- OSWorld 2.0 ---------------------------------------------------------------------

export interface OsRow {
  rank: number;
  model: string;
  org: string | null;
  provider: ProviderKey;
  reasoning: string | null;
  tool: string | null;
  steps: number | null;
  release: string | null;
  /** Binary accuracy (success rate) and partial score, in percent. */
  binary: number;
  partial: number | null;
  costPerTask: number | null;
  official: boolean | null;
  change: BenchmarkChange | null;
  changeBy: number;
}

/** The rows of the site's default table, in its order. */
export function osWorldView(site: BenchmarkSite): OsRow[] {
  return site.rows
    .filter((row) => defaultRank(row) !== null)
    .map(
      (row): OsRow => ({
        rank: defaultRank(row) as number,
        model: row.model,
        org: row.org,
        provider: provider(row.org, row.model),
        reasoning: row.config,
        tool: extraString(row, "tool_setting"),
        steps: extraNumber(row, "step_budget"),
        release: extraString(row, "release_version"),
        binary: row.value,
        partial: extraNumber(row, "partial_score"),
        costPerTask: r2n(extraNumber(row, "cost_per_task"), 3),
        official: typeof row.extra.official === "boolean" ? row.extra.official : null,
        change: row.change,
        changeBy: row.change_by,
      }),
    )
    .sort(byDefaultRank);
}

// ---- τ²-bench ------------------------------------------------------------------------

export interface Tau2Row {
  id: string;
  board: string;
  /** Rank by pass^1 among the board's standard submissions (the site's default). */
  rank: number | null;
  model: string;
  /** Who submitted it (the site's organisation column); for voice the provider. */
  submitter: string | null;
  modelOrg: string | null;
  provider: ProviderKey;
  effort: string | null;
  /** pass^1..pass^4 in percent. */
  passes: (number | null)[];
  verified: boolean;
  custom: boolean;
  release: string | null;
  retrieval: string | null;
  change: BenchmarkChange | null;
  changeBy: number;
}

export interface Tau2View {
  boards: string[];
  updated: Record<string, string>;
  rows: Tau2Row[];
}

export function tau2View(site: BenchmarkSite): Tau2View {
  const rows = site.rows
    .filter((row) => row.metric === "pass_1")
    .map(
      (row): Tau2Row => ({
        id: `${row.board}|${extraString(row, "entry") ?? row.model}`,
        board: row.board,
        rank: defaultRank(row),
        model: row.model,
        submitter: extraString(row, "voice_provider") ?? extraString(row, "submitting_org"),
        modelOrg: row.org,
        provider: provider(row.org, row.model),
        effort: row.config,
        passes: [r2(row.value), r2n(extraNumber(row, "pass_2")), r2n(extraNumber(row, "pass_3")), r2n(extraNumber(row, "pass_4"))],
        verified: row.extra.verified === true,
        custom: extraString(row, "submission_type") === "custom",
        release: extraString(row, "release_date"),
        retrieval: extraString(row, "retrieval_config"),
        change: row.change,
        changeBy: row.change_by,
      }),
    )
    .sort(byDefaultRank);
  const present = new Set(rows.map((r) => r.board));
  return { boards: TAU2_BOARDS.map((b) => b.key as string).filter((b) => present.has(b)), updated: site.updated ?? {}, rows };
}

// ---- Epoch AI ------------------------------------------------------------------------

/** Rows per board the card carries; the site opens on 20 and shows more on request. */
export const EPOCH_ROWS = 50;

export interface EpochRow {
  rank: number;
  model: string;
  org: string | null;
  provider: ProviderKey;
  /** A 0-1 share, minutes (METR) or index points (ECI), as `unit` says. */
  value: number;
  low: number | null;
  high: number | null;
  source: string | null;
  change: BenchmarkChange | null;
  changeBy: number;
}

export interface EpochBoard {
  key: string;
  unit: "percent" | "minutes" | "index";
  updated: string | null;
  /** How many models the board ranks (only the first EPOCH_ROWS ride along). */
  total: number;
  rows: EpochRow[];
}

const EPOCH_ORDER = ["eci", "gpqa_diamond", "frontiermath_tiers_1_3", "frontiermath_tier_4", "hle", "arc_agi_2", "swe_bench_verified", "metr_time_horizons", "cursorbench", "gdpval"];

export function epochView(site: BenchmarkSite): EpochBoard[] {
  const boards = new Map<string, EpochBoard>();
  for (const row of site.rows) {
    const rank = defaultRank(row);
    if (rank === null) continue;
    let board = boards.get(row.board);
    if (!board) {
      const unit = extraString(row, "unit");
      board = { key: row.board, unit: unit === "minutes" || unit === "index" ? unit : "percent", updated: site.updated?.[row.board] ?? null, total: 0, rows: [] };
      boards.set(row.board, board);
    }
    board.total += 1;
    const digits = board.unit === "percent" ? 4 : 2;
    board.rows.push({
      rank,
      model: row.model,
      org: row.org,
      provider: provider(row.org, row.model),
      value: round(row.value, digits),
      low: r2n(row.ci_low, digits),
      high: r2n(row.ci_high, digits),
      source: extraString(row, "source_link") ?? extraString(row, "source"),
      change: row.change,
      changeBy: row.change_by,
    });
  }
  for (const board of boards.values()) board.rows = board.rows.sort(byDefaultRank).slice(0, EPOCH_ROWS);
  const order = (key: string) => (EPOCH_ORDER.includes(key) ? EPOCH_ORDER.indexOf(key) : EPOCH_ORDER.length);
  return [...boards.values()].sort((a, b) => order(a.key) - order(b.key));
}

// ---- all sites -----------------------------------------------------------------------

export interface BenchmarkViews {
  deepswe?: DeepSweView;
  livebench?: LiveModel[];
  lmarena?: ArenaView;
  artificial_analysis?: AaModel[];
  terminal_bench?: TbView;
  osworld?: OsRow[];
  tau2?: Tau2View;
  epoch?: EpochBoard[];
}

export function projectViews(sites: Partial<Record<BenchmarkSiteKey, BenchmarkSite>>): BenchmarkViews {
  const views: BenchmarkViews = {};
  for (const key of BENCHMARK_SITES) {
    const site = sites[key];
    if (!site) continue;
    if (key === "deepswe") views.deepswe = deepSweView(site);
    else if (key === "livebench") views.livebench = liveBenchModels(site);
    else if (key === "lmarena") views.lmarena = lmArenaView(site);
    else if (key === "terminal_bench") views.terminal_bench = terminalBenchView(site);
    else if (key === "osworld") views.osworld = osWorldView(site);
    else if (key === "tau2") views.tau2 = tau2View(site);
    else if (key === "epoch") views.epoch = epochView(site);
    else views.artificial_analysis = aaModels(site);
  }
  return views;
}

// ---- how the newer sites print their numbers -----------------------------------------

/** tbench.ai: tokens in billions with one decimal ("8.0B"), "—" for none. */
export function tbTokens(value: number | null): string {
  return value !== null && value > 0 ? `${(value / 1e9).toFixed(1)}B` : "—";
}

/** tbench.ai: cost in thousands of dollars with one decimal ("$4.7k", "$0.6k"), "—" for none. */
export function tbCost(value: number | null): string {
  return value !== null && value > 0 ? `$${(value / 1e3).toFixed(1)}k` : "—";
}

/** osworld-v2.xlang.ai's formatPercent: two decimals unless one is exact ("44.33%", "20.6%"). */
export function osPercent(value: number | null): string {
  if (value === null) return "—";
  const decimals = Math.abs(value * 10 - Math.round(value * 10)) > 1e-8 ? 2 : 1;
  return `${value.toFixed(decimals)}%`;
}

/** epoch.ai's formatDurationMinutes: "17 hr 25 min", "59 min 18 sec", "45 sec". */
export function formatDurationMinutes(minutes: number): string {
  if (minutes >= 60) {
    const whole = Math.round(minutes);
    const hours = Math.floor(whole / 60);
    const rest = whole % 60;
    return rest === 0 ? `${hours} hr` : `${hours} hr ${rest} min`;
  }
  const seconds = Math.round(minutes * 60);
  if (seconds >= 3600) return "1 hr";
  const wholeMinutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (wholeMinutes === 0) return `${rest} sec`;
  return rest === 0 ? `${wholeMinutes} min` : `${wholeMinutes} min ${rest} sec`;
}

/** An Epoch score as its leaderboard prints it: a share in percent with one decimal, METR as a
 * duration, the ECI whole. */
export function epochScore(value: number, unit: EpochBoard["unit"]): string {
  if (unit === "minutes") return formatDurationMinutes(value);
  if (unit === "index") return value.toFixed(0);
  return `${(value * 100).toFixed(1)}%`;
}
