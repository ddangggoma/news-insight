/** AI model leaderboards (plan 18 part 2): the shape of GET /api/public/benchmarks. */

export const BENCHMARK_SITES = ["deepswe", "livebench", "lmarena", "artificial_analysis"] as const;
export type BenchmarkSiteKey = (typeof BENCHMARK_SITES)[number];

export const SITE_TITLE: Record<BenchmarkSiteKey, string> = {
  deepswe: "DeepSWE",
  livebench: "LiveBench",
  lmarena: "LMArena",
  artificial_analysis: "Artificial Analysis",
};

/** What each card measures, in one line. */
export const SITE_BLURB: Record<BenchmarkSiteKey, string> = {
  deepswe: "긴 소프트웨어 엔지니어링 과제를 코딩 에이전트가 한 번에 통과하는 비율(pass@1)",
  livebench: "에이전틱·코딩·추론 등 영역별 오염 방지 문제 점수",
  lmarena: "사람이 두 모델의 답을 나란히 보고 고른 투표로 매긴 점수",
  artificial_analysis: "자체 평가 묶음의 지능 지수와 가격·출력 속도",
};

export type BenchmarkChange = "new" | "up" | "down" | "same";

export interface BenchmarkRow {
  board: string;
  /** The site's own spelling. */
  model: string;
  model_id: number | null;
  org: string | null;
  config: string | null;
  metric: string;
  value: number;
  ci_low: number | null;
  ci_high: number | null;
  extra: Record<string, unknown>;
  /** Set only on a model's best row on the board's representative metric. */
  rank: number | null;
  change: BenchmarkChange | null;
  change_by: number;
}

export interface BenchmarkSite {
  site: string;
  title: string;
  source_url: string;
  license: string;
  attribution: string;
  release: string;
  /** Last time the collector saw this snapshot. */
  fetched_at: string;
  /** Not seen for more than 48 hours. */
  stale: boolean;
  boards: string[];
  rows: BenchmarkRow[];
}

export function isSiteKey(raw: string): raw is BenchmarkSiteKey {
  return (BENCHMARK_SITES as readonly string[]).includes(raw);
}

/** LMArena boards we collect, with the reader's tab label. */
export const LMARENA_BOARD_LABEL: Record<string, string> = {
  text_style_control: "텍스트",
  webdev: "웹개발",
  vision_style_control: "비전",
  search_style_control: "검색",
  agent: "에이전트",
};

/** LiveBench's table.csv columns in the site's column order, with its header labels. */
export const LIVEBENCH_CATEGORIES = [
  { key: "long_agentic", label: "에이전틱", site: "Agentic" },
  { key: "design", label: "디자인", site: "Design" },
  { key: "coding", label: "코딩", site: "Coding" },
  { key: "browser", label: "브라우저 사용", site: "Browser Use" },
  { key: "data_analysis", label: "데이터 분석", site: "Data Analysis" },
  { key: "research", label: "리서치", site: "Research" },
  { key: "reasoning", label: "추론", site: "Reasoning" },
] as const;

/** Artificial Analysis metrics the charts plot (the API names them; the full rows carry ~60). */
export const AA_METRICS = {
  intelligence: "artificial_analysis_intelligence_index",
  price: "price_1m_blended_3_to_1",
  speed: "median_output_tokens_per_second",
} as const;

export function boardLabel(site: string, board: string): string {
  if (site === "lmarena") return LMARENA_BOARD_LABEL[board] ?? board;
  if (site === "livebench" && board === "main") return "종합";
  if (site === "artificial_analysis" && board === "language") return "언어 모델";
  return board;
}

/** A finite number from a row's `extra`, else null. */
export function extraNumber(row: Pick<BenchmarkRow, "extra">, key: string): number | null {
  const value = row.extra[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function extraString(row: Pick<BenchmarkRow, "extra">, key: string): string | null {
  const value = row.extra[key];
  return typeof value === "string" && value ? value : null;
}

/** Name prefixes that tell the maker; used only to colour a mark when a site gives no organisation. */
const ORG_BY_PREFIX: [RegExp, string][] = [
  [/^(claude|anthropic)/i, "Anthropic"],
  [/^(gpt|o\d|chatgpt|openai|codex)/i, "OpenAI"],
  [/^(gemini|gemma|google)/i, "Google"],
  [/^grok/i, "xAI"],
  [/^(llama|meta)/i, "Meta"],
  [/^deepseek/i, "DeepSeek"],
  [/^(qwen|qwq|alibaba)/i, "Alibaba"],
  [/^(mistral|magistral|devstral|codestral|ministral)/i, "Mistral"],
  [/^kimi/i, "Moonshot AI"],
  [/^glm/i, "Z AI"],
  [/^minimax/i, "MiniMax"],
];

/** The row's organisation, else a guess from the model name (colour only, never shown as data). */
export function colourOrg(org: string | null, model: string): string | null {
  if (org) return org;
  const name = model.trim();
  return ORG_BY_PREFIX.find(([pattern]) => pattern.test(name))?.[1] ?? null;
}

/** Licences that say nothing about openness. */
const CLOSED_OR_UNKNOWN = new Set(["", "proprietary", "unknown", "n/a", "na", "none", "-"]);

/** LMArena: open only when the licence column names an actual licence. */
export function isOpenLicense(license: string | null | undefined): boolean {
  return typeof license === "string" && !CLOSED_OR_UNKNOWN.has(license.trim().toLowerCase());
}

/** Newest version first: "v1.1" before "v1" (boards are named by benchmark version). */
export function newestBoardFirst(boards: string[]): string[] {
  const parts = (b: string) => (b.match(/\d+/g) ?? []).map(Number);
  return [...boards].sort((a, b) => {
    const [x, y] = [parts(a), parts(b)];
    for (let i = 0; i < Math.max(x.length, y.length); i++) {
      const diff = (y[i] ?? -1) - (x[i] ?? -1);
      if (diff !== 0) return diff;
    }
    return 0;
  });
}

/** Models that entered a board today, from the summary (top 10 per board). */
export function newModels(sites: BenchmarkSite[]): { site: string; title: string; board: string; model: string; rank: number }[] {
  return sites.flatMap((site) =>
    site.rows
      .filter((row) => row.change === "new" && row.rank !== null)
      .map((row) => ({ site: site.site, title: site.title, board: row.board, model: row.model, rank: row.rank as number })),
  );
}

export function formatUsd(value: number | null): string {
  if (value === null) return "—";
  if (value >= 100) return `$${value.toFixed(0)}`;
  if (value >= 1) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(3)}`;
}

/** 46977 → "47.0K", 1250000 → "1.25M". */
export function formatCompact(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}
