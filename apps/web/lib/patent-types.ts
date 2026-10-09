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
