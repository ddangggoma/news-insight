// Public reader API (/api/public) — mirrors apps/api/src/news_insight/reader/schemas.py.
import type { StrategyClaim, Track } from "@/lib/types";

export interface ReaderCard {
  id: number;
  title: string;
  title_ko: string | null;
  summary_ko: string[];
  keywords: string[];
  url: string;
  source_name: string;
  track: Track;
  category: string;
  region: string;
  published_at: string | null;
  first_seen_at: string;
  field: string | null;
  themes: string[];
  businesses: string[];
  impact: string | null;
  relevance: number | null;
  coverage: number | null;
}

export interface ItemRef {
  id: number;
  title: string;
  url: string;
  source_name: string;
  track: Track;
}

export interface ReaderInsight {
  title: string;
  body: string;
  item_ids: number[];
}

export interface ReaderPersona {
  key: string;
  name: string;
  group: "executive" | "business" | "domain";
  status: "insight" | "no_signal";
  headline: string;
  insight: string;
  actions: string[];
  item_ids: number[];
}

export interface StrategyReport {
  summary: string;
  businesses: { business: string; summary: string; claims: StrategyClaim[] }[];
  roadmap: (StrategyClaim & { horizon: "1y" | "3y" | "5y" })[];
  opportunities: StrategyClaim[];
  risks: StrategyClaim[];
}

export interface ReaderBriefing {
  briefing_date: string;
  version: number;
  published_at: string;
  headline: string | null;
  overview: string | null;
  insights: ReaderInsight[];
  sections: { track: Track; summary: string | null; items: ReaderCard[] }[];
  strategy: {
    personas: ReaderPersona[];
    report: StrategyReport | null;
    review_verdict: string | null;
    dropped_claims: number;
  } | null;
  refs: ItemRef[];
  gates_passed: number;
  gates_total: number;
  previous_date: string | null;
  next_date: string | null;
}

export interface ArchiveEntry {
  briefing_date: string;
  version: number;
  headline: string | null;
  items: number;
  published_at: string;
}

export interface ReaderPage<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface TaxonomyCounts {
  window_days: number;
  total: number;
  fields: Record<string, number>;
  themes: Record<string, number>;
  businesses: Record<string, number>;
  impacts: Record<string, number>;
}
