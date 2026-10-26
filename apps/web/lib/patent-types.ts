import type { CompanyRef, FeedPage } from "@/lib/reader-types";

export interface PatentTrend {
  key: string;
  label: string;
  axis: "field" | "theme" | "company";
  counts: number[];
  current: number;
  previous: number;
}

export interface PatentView {
  kind: "month" | "quarter";
  periods: { key: string; total: number; office: number }[];
  nodes: PatentTrend[];
  companies: (PatentTrend & { company: CompanyRef })[];
  recent: FeedPage;
}

/** "+3", "-2", "새로", "–" for a change between two periods. */
export function changeLabel(current: number, previous: number): string {
  if (previous === 0) return current > 0 ? "새로" : "–";
  const diff = current - previous;
  return diff === 0 ? "0" : `${diff > 0 ? "+" : ""}${diff}`;
}

/** An article's date for display: its own date when the API gives one, else when it was published or first seen. */
export function articleDate(item: { occurred_at?: string | null; published_at: string | null; first_seen_at: string }): string {
  return item.occurred_at ?? item.published_at ?? item.first_seen_at;
}

export interface PatentSummary {
  current: { key: string; total: number; office: number } | null;
  previous: { key: string; total: number; office: number } | null;
  /** Change of the current (still running) period against the previous one, as a ratio (null: no base). */
  change: number | null;
  total: number;
  office: number;
  officeShare: number | null;
  riser: PatentTrend | null;
}

/** Headline figures for the tiles: this period, its change, the office share and the fastest riser. */
export function patentSummary(view: PatentView): PatentSummary {
  const periods = view.periods;
  const current = periods.at(-1) ?? null;
  const previous = periods.at(-2) ?? null;
  const total = periods.reduce((sum, p) => sum + p.total, 0);
  const office = periods.reduce((sum, p) => sum + p.office, 0);
  const risers = [...view.nodes, ...view.companies]
    .filter((t) => t.current > t.previous && t.current >= 2)
    .sort((a, b) => b.current - b.previous - (a.current - a.previous) || b.current - a.current);
  return {
    current,
    previous,
    change: current && previous && previous.total > 0 ? (current.total - previous.total) / previous.total : null,
    total,
    office,
    officeShare: total ? office / total : null,
    riser: risers[0] ?? null,
  };
}

/** "2026-10" → "26.10", "2026-Q3" → "26 Q3". */
export function periodLabel(key: string): string {
  return key.includes("Q") ? `${key.slice(2, 4)} ${key.slice(5)}` : `${key.slice(2, 4)}.${key.slice(5, 7)}`;
}
