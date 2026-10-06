// Published briefing (/api/public/briefings) — mirrors apps/api/src/news_insight/public/briefings.py.
import type { CompanyRelation, ReaderItem } from "@/lib/reader-types";
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
  group: "practitioner" | "executive" | "business" | "domain";
  status: "insight" | "no_signal";
  headline: string;
  insight: string;
  actions: string[];
  item_ids: number[];
  /** How much today's articles matter to the role (0-100, plan 13 B6). */
  relevance?: number;
  stances?: { theme: string; stance: "opportunity" | "risk" | "watch" }[];
}

export interface StrategyReport {
  summary: string;
  fields: { field: string; summary: string; claims: StrategyClaim[] }[];
  roadmap: (StrategyClaim & { horizon: "1y" | "3y" | "5y" })[];
  opportunities: StrategyClaim[];
  risks: StrategyClaim[];
}

export interface BriefingSignal {
  tone: string;
  title: string;
  detail: string;
  window_key: string;
  is_current: boolean;
  href: string;
}

/** How well an insight or claim is supported: computed from its evidence (plan 13 B2). */
export interface Strength {
  grade: "strong" | "medium" | "weak";
  outlets: number;
  tracks: number;
  regions: number;
  vendor_share: number;
  reason: string;
}

export type Continuity = "new" | "continuing" | "escalation" | "reversal";

export interface BriefingInsight {
  title: string;
  body: string;
  item_ids: number[];
  continuity: Continuity;
  previous_title: string | null;
  companies: string[];
  strength: Strength | null;
}

export interface ContinuingStory {
  story_id: number;
  item_id: number;
  title: string;
  days: number;
  sources: number;
}

export interface CompanyMove {
  key: string;
  label: string;
  relation: CompanyRelation;
  kind: string;
  count: number;
  item_ids: number[];
}

export interface DigestTrack {
  track: Track;
  summary: string;
  categories: { category: string; headline: string; points: { text: string; item_ids: number[] }[] }[];
}

export interface PublicBriefing {
  briefing_date: string;
  version: number;
  published_at: string;
  headline: string | null;
  tldr: string[];
  overview: string | null;
  insights: BriefingInsight[];
  continuing: ContinuingStory[];
  companies: CompanyMove[];
  digest_tracks: DigestTrack[];
  sections: { track: Track; summary: string | null; items: ReaderItem[] }[];
  strategy: {
    personas: BriefingPersona[];
    default_persona?: string;
    /** Themes some roles read as an opportunity and others as a risk. */
    conflicts?: { theme: string; opportunity: string[]; risk: string[] }[];
    report: StrategyReport | null;
    review_verdict: string | null;
    dropped_claims: number;
  } | null;
  /** Radar cards stored for the briefing date (PRD-1), linked to the radar. */
  signals?: BriefingSignal[];
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
