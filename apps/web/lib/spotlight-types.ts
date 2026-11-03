import { formatNumber } from "@/lib/format";

/** The daily Top 10 sections, in the order the page shows them. */
export const SECTION_KEYS = ["news", "product", "oss", "interview", "community", "research", "patent"] as const;
export type SectionKey = (typeof SECTION_KEYS)[number];

export const SECTION_LABEL: Record<SectionKey, string> = {
  news: "뉴스",
  product: "제품",
  oss: "오픈소스",
  interview: "인터뷰·발언",
  community: "커뮤니티",
  research: "연구",
  patent: "특허",
};

export interface SpotlightEntry {
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

/** The page's tabs. The AI model tab (part 2) joins this list. */
export const SPOTLIGHT_TABS = [
  { key: "overview", label: "전체" },
  ...SECTION_KEYS.map((key) => ({ key, label: SECTION_LABEL[key] })),
] as const;
export type SpotlightTab = (typeof SPOTLIGHT_TABS)[number]["key"];

export function parseTab(raw: string | undefined): SpotlightTab {
  return SPOTLIGHT_TABS.find((tab) => tab.key === raw)?.key ?? "overview";
}

/** The page's address for a tab and day; the default tab and an unset day stay out of it. */
export function spotlightHref(tab: SpotlightTab, date: string | null): string {
  const query = [tab === "overview" ? null : `tab=${tab}`, date ? `date=${date}` : null].filter(Boolean).join("&");
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
};

/** Internal ranking inputs: they mean nothing to a reader. */
const HIDDEN_METRICS = new Set(["community_z"]);

/** Short chips for an entry's raw metrics: Korean labels where obvious, the key itself otherwise. */
export function metricChips(metrics: Record<string, number | string>): string[] {
  const chips: string[] = [];
  for (const [key, value] of Object.entries(metrics)) {
    if (HIDDEN_METRICS.has(key)) continue;
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
