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

// ---- all sites -----------------------------------------------------------------------

export interface BenchmarkViews {
  deepswe?: DeepSweView;
  livebench?: LiveModel[];
  lmarena?: ArenaView;
  artificial_analysis?: AaModel[];
}

export function projectViews(sites: Partial<Record<BenchmarkSiteKey, BenchmarkSite>>): BenchmarkViews {
  const views: BenchmarkViews = {};
  for (const key of BENCHMARK_SITES) {
    const site = sites[key];
    if (!site) continue;
    if (key === "deepswe") views.deepswe = deepSweView(site);
    else if (key === "livebench") views.livebench = liveBenchModels(site);
    else if (key === "lmarena") views.lmarena = lmArenaView(site);
    else views.artificial_analysis = aaModels(site);
  }
  return views;
}
