import type { CompanyRef } from "@/lib/reader-types";

export interface DossierSummary {
  id: number;
  title: string;
  description: string | null;
  recent: number;
  total: number;
  hypotheses: number;
  updated_at: string;
  updated_by: string | null;
}

export interface DossierCriteria {
  nodes: string[];
  companies: CompanyRef[];
  keywords: string[];
  exclude: string[];
  statement: string | null;
  min_similarity: number;
  semantic_active: boolean;
}

export interface TimelineStory {
  item_id: number;
  title: string;
  source_count: number;
  first_seen_at: string;
}

export interface TimelineWeek {
  week: string;
  items: number;
  stories: number;
  top: TimelineStory[];
}

export interface Evidence {
  id: number;
  item_id: number;
  title: string;
  source: string;
  url: string;
  first_seen_at: string;
  stance: Stance;
  note: string | null;
  added_by: string | null;
}

export type Stance = "support" | "oppose" | "context";
export type HypothesisStatus = "open" | "supported" | "refuted" | "mixed";

export interface Hypothesis {
  id: number;
  text: string;
  status: HypothesisStatus;
  counts: Record<Stance, number>;
  evidence: Evidence[];
}

export interface Suggestion {
  item_id: number;
  title: string;
  source: string;
  url: string;
  first_seen_at: string;
  similarity: number;
}

export interface DossierDetail {
  id: number;
  title: string;
  description: string | null;
  criteria: DossierCriteria;
  created_by: string | null;
  updated_by: string | null;
  updated_at: string;
  total: number;
  changes: {
    recent: number;
    previous: number;
    new_companies: CompanyRef[];
    signals: { key: string; now: number; before: number }[];
    top: TimelineStory[];
  };
  timeline: TimelineWeek[];
  companies: { company: CompanyRef; count: number }[];
  figures: { item_id: number; text: string; source: string; first_seen_at: string }[];
  hypotheses: Hypothesis[];
}

export const STANCE_LABEL: Record<Stance, string> = { support: "찬성", oppose: "반대", context: "참고" };
export const STATUS_LABEL: Record<HypothesisStatus, string> = {
  open: "검토 중",
  supported: "지지됨",
  refuted: "기각됨",
  mixed: "엇갈림",
};

/** "a, b , c" → ["a", "b", "c"] without blanks or repeats. */
export function splitList(value: string): string[] {
  return [...new Set(value.split(/[,\n]/).map((v) => v.trim()).filter(Boolean))];
}
