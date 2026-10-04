// Published briefing (/api/public/briefings) — mirrors apps/api/src/news_insight/public/briefings.py.
import type { ReaderItem } from "@/lib/reader-types";
import type { StrategyClaim, Track } from "@/lib/types";

export interface ItemRef {
  id: number;
  title: string;
  url: string;
  source_name: string;
  track: Track;
}

export interface BriefingPersona {
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

export interface PublicBriefing {
  briefing_date: string;
  version: number;
  published_at: string;
  headline: string | null;
  overview: string | null;
  insights: { title: string; body: string; item_ids: number[] }[];
  sections: { track: Track; summary: string | null; items: ReaderItem[] }[];
  strategy: {
    personas: BriefingPersona[];
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

export interface BriefingEntry {
  briefing_date: string;
  version: number;
  headline: string | null;
  items: number;
  published_at: string;
}
