import { formatNumber } from "@/lib/format";

/** The daily sections (24 h Top 10 and sustained Top 5 each), in the order the page shows them. */
export const SECTION_KEYS = ["news", "product", "ai", "oss", "interview", "community", "research", "patent"] as const;
export type SectionKey = (typeof SECTION_KEYS)[number];

export const SECTION_LABEL: Record<SectionKey, string> = {
  news: "뉴스",
  product: "제품",
  ai: "AI 모델·서비스",
  oss: "오픈소스",
  interview: "인터뷰·발언",
  community: "커뮤니티",
  research: "연구",
  patent: "특허",
};

/** 최근 24시간 (the day's window) and 지속 주목 (attention held over several of the last 7 days). */
export const GROUP_KEYS = ["now", "sustained"] as const;
export type GroupKey = (typeof GROUP_KEYS)[number];
export const GROUP_LABEL: Record<GroupKey, string> = { now: "최근 24시간", sustained: "지속 주목" };

export interface SpotlightEntry {
  /** Missing from lists published before the groups: read as "now". */
  group?: GroupKey;
  /** Within the group. */
  rank: number;
  /** Rank by the statistical score, before Opus moved the entry. */
  stat_rank: number;
  change: "new" | "up" | "down" | "same";
  change_by: number;
  key: string;
  item_ids: number[];
  title_ko: string;
  product_name: string | null;
  summary: string;
  why_hot: string;
  rank_note: string | null;
  metrics: Record<string, number | string>;
  /** True when Opus did not write this entry (statistical order and card text). */
  fallback: boolean;
  url: string | null;
  /** Opus's short insight tags ("가격 인하", "첫 공개"). */
  tags?: string[];
  /** The server's tags from the numbers ("보도 7곳", "7일 중 4일"). */
  signals?: string[];
  /** Technology field of the lead card, with its Korean label. */
  field?: string | null;
  field_label?: string | null;
}

export const groupOf = (entry: Pick<SpotlightEntry, "group">): GroupKey => (entry.group === "sustained" ? "sustained" : "now");

/** A section's entries split into its two groups, each in rank order. */
export function splitGroups(entries: SpotlightEntry[]): Record<GroupKey, SpotlightEntry[]> {
  const byRank = (a: SpotlightEntry, b: SpotlightEntry) => a.rank - b.rank;
  return {
    now: entries.filter((entry) => groupOf(entry) === "now").sort(byRank),
    sustained: entries.filter((entry) => groupOf(entry) === "sustained").sort(byRank),
  };
}

/** The list filters kept in the address: a technology field and a group (null: all). */
export interface SpotlightFilters {
  field: string | null;
  group: GroupKey | null;
}

export function parseFilters(field: string | undefined, group: string | undefined): SpotlightFilters {
  return {
    field: field && /^[a-z0-9_]{1,40}$/.test(field) ? field : null,
    group: GROUP_KEYS.find((key) => key === group) ?? null,
  };
}

export function filterEntries(entries: SpotlightEntry[], filters: SpotlightFilters): SpotlightEntry[] {
  return entries.filter((entry) => (!filters.field || entry.field === filters.field) && (!filters.group || groupOf(entry) === filters.group));
}

/** The fields present among `entries`, most entries first (ties by label), with their counts. */
export function fieldCounts(entries: SpotlightEntry[]): { key: string; label: string; count: number }[] {
  const found = new Map<string, { key: string; label: string; count: number }>();
  for (const entry of entries) {
    if (!entry.field) continue;
    const seen = found.get(entry.field);
    if (seen) seen.count += 1;
    else found.set(entry.field, { key: entry.field, label: entry.field_label || entry.field, count: 1 });
  }
  return [...found.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko"));
}

export interface SpotlightView {
  /** Null while nothing has been published yet. */
  date: string | null;
  generating: boolean;
  headline: string;
  benchmark_note: string;
  sections: Record<SectionKey, SpotlightEntry[]>;
  /** Published days, newest first. */
  available_dates: string[];
  generated_at: string | null;
}

/** The page's tabs: the overview and one per section (AI 모델·서비스 also holds the benchmarks). */
export const SPOTLIGHT_TABS = [{ key: "overview", label: "전체" }, ...SECTION_KEYS.map((key) => ({ key, label: SECTION_LABEL[key] }))] as const;
export type SpotlightTab = (typeof SPOTLIGHT_TABS)[number]["key"];

/** The tab key of the former 「AI 모델」 tab (until 2026-11-04); its benchmarks are under `ai` now. */
export const RETIRED_MODELS_TAB = "models";

export function parseTab(raw: string | undefined): SpotlightTab {
  if (raw === RETIRED_MODELS_TAB) return "ai";
  return SPOTLIGHT_TABS.find((tab) => tab.key === raw)?.key ?? "overview";
}

/** True for a real calendar day written YYYY-MM-DD (2026-13-45 is well formed but not a day). */
export function isCalendarDay(raw: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

/** The page's address for a tab and day (and filters); the defaults stay out of it. */
export function spotlightHref(tab: SpotlightTab, date: string | null, filters?: SpotlightFilters): string {
  const query = [
    tab === "overview" ? null : `tab=${tab}`,
    date ? `date=${date}` : null,
    filters?.field ? `field=${encodeURIComponent(filters.field)}` : null,
    filters?.group ? `group=${filters.group}` : null,
  ]
    .filter(Boolean)
    .join("&");
  return query ? `/spotlight?${query}` : "/spotlight";
}

const METRIC_LABEL: Record<string, (n: string) => string> = {
  source_count: (n) => `보도 ${n}곳`,
  community_mentions: (n) => `언급 ${n}`,
  mentions: (n) => `언급 ${n}`,
  upvotes: (n) => `추천 ${n}`,
  views: (n) => `조회 ${n}`,
  points: (n) => `점수 ${n}`,
  score: (n) => `점수 ${n}`,
  comments: (n) => `댓글 ${n}`,
  replies: (n) => `답글 ${n}`,
  answers: (n) => `답변 ${n}`,
  stars: (n) => `별 ${n}`,
  trending_stars_daily: (n) => `오늘 별 +${n}`,
  likes: (n) => `좋아요 ${n}`,
  favourites: (n) => `좋아요 ${n}`,
  reactions: (n) => `반응 ${n}`,
  reposts: (n) => `재공유 ${n}`,
  reblogs: (n) => `재공유 ${n}`,
  downloads: (n) => `다운로드 ${n}`,
  trending: (n) => `트렌딩 ${n}`,
  group_size: (n) => `묶음 ${n}건`,
};

/** Internal ranking inputs: they mean nothing to a reader. */
const HIDDEN_METRICS = new Set(["community_z", "basis", "trend_rank", "best_rank", "days_active", "listed_days"]);

/** Shown by the trend chip instead, when there is one. */
const TREND_METRICS = new Set(["rank", "from", "site", "board"]);

/** Why a trend-listed entry is there: the trending list or leaderboard it came from. */
export function trendChip(metrics: Record<string, number | string>): string | null {
  const rank = metrics.trend_rank;
  const place = typeof rank === "number" && Number.isFinite(rank) ? Math.round(rank) : null;
  switch (metrics.basis) {
    case "github_daily":
      return place ? `GitHub 트렌딩 ${place}위` : "GitHub 트렌딩";
    case "github_weekly":
      return place ? `GitHub 주간 트렌딩 ${place}위` : "GitHub 주간 트렌딩";
    case "hf_trending":
      return "HF 트렌딩";
    case "benchmark": {
      const site = typeof metrics.site === "string" ? metrics.site : "벤치마크";
      const at = typeof metrics.rank === "number" ? ` ${Math.round(metrics.rank)}위` : "";
      return `${site}${at}`;
    }
    default:
      return null;
  }
}

/** Signals that restate the trend chip (list rank, HF trending, leaderboard rank). */
const TREND_SIGNAL = /^(?:GitHub(?: 주간)? \d+위|HF 트렌딩|벤치마크 \d+위)$/;

/** The server's signals worth showing beside the row's chips: none repeating its trend chip. */
export function visibleSignals(entry: Pick<SpotlightEntry, "signals" | "metrics">): string[] {
  const signals = entry.signals ?? [];
  return trendChip(entry.metrics) ? signals.filter((signal) => !TREND_SIGNAL.test(signal)) : signals;
}

/** Short chips for an entry's raw metrics: Korean labels where obvious, the key itself otherwise. */
export function metricChips(metrics: Record<string, number | string>): string[] {
  const chips: string[] = [];
  const trend = trendChip(metrics);
  if (trend) chips.push(trend);
  for (const [key, value] of Object.entries(metrics)) {
    if (HIDDEN_METRICS.has(key) || (trend && TREND_METRICS.has(key))) continue;
    if (key === "platform") {
      if (typeof value === "string" && value) chips.push(value);
      continue;
    }
    if (typeof value !== "number" || !Number.isFinite(value) || value === 0) continue;
    const text = formatNumber(Math.round(value));
    chips.push(METRIC_LABEL[key]?.(text) ?? `${key} ${text}`);
  }
  return chips;
}
