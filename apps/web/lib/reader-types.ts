// Mirrors apps/api/src/news_insight/public/schemas.py
import type { DigestOut, Region, Track } from "@/lib/types";

export interface StoryBrief {
  id: number;
  item_count: number;
  source_count: number;
  tracks: string[];
}

export interface ReaderItem {
  id: number;
  url: string;
  title: string;
  title_ko: string | null;
  summary_ko: string[];
  keywords: string[];
  field: string | null;
  themes: string[];
  businesses: string[];
  impact: string | null;
  scope: string | null;
  relevance: number | null;
  track: Track;
  source_name: string;
  region: Region;
  published_at: string | null;
  first_seen_at: string;
  metrics: Record<string, number>;
  story: StoryBrief | null;
}

export interface FeedPage {
  items: ReaderItem[];
  total: number;
  items_total: number;
  page: number;
  size: number;
}

export interface LinkedItem {
  id: number;
  url: string;
  title: string;
  title_ko: string | null;
  track: Track;
  source_name: string;
  first_seen_at: string;
  ref: string | null;
}

export interface ReaderItemDetail {
  item: ReaderItem;
  story_items: LinkedItem[];
  signals: LinkedItem[];
  same_field: LinkedItem[];
}

export type Facets = Record<"field" | "theme" | "business" | "impact" | "track" | "region" | "scope", Record<string, number>>;

export interface Count {
  key: string;
  count: number;
}

export interface KeywordTrend {
  key: string;
  label: string;
  count: number;
  previous: number | null;
  change: number | null;
  is_new: boolean;
}

export interface Insights {
  total: number;
  previous_total: number | null;
  keywords: KeywordTrend[];
  related_keywords: string[];
  fields: Count[];
  businesses: Count[];
  impacts: Count[];
}

export type RadarKind = "day" | "week" | "month" | "quarter";

export interface RadarWindow {
  kind: RadarKind;
  key: string;
  start: string;
  end: string;
  prev_key: string;
  next_key: string;
  is_current: boolean;
}

export interface Cell {
  field: string;
  business: string;
  count: number;
  previous: number;
}

export interface Radar {
  window: RadarWindow;
  kpis: {
    total: number;
    previous_total: number;
    new_stories: number;
    cross_track_stories: number;
    hottest: Cell | null;
  };
  cells: Cell[];
  momentum: { key: string; counts: number[]; change: number | null }[];
  hype: { key: string; chatter: number; chatter_change: number | null; research: number; research_change: number | null }[];
  keywords: { key: string; label: string; state: "new" | "rising" | "steady" | "falling"; counts: number[] }[];
}

export interface CellDetail {
  field: string;
  business: string;
  count: number;
  previous: number;
  trend: number[];
  themes: Count[];
  keywords: { key: string; label: string; count: number }[];
  stories: ReaderItem[];
}

export type PublicDigest = Omit<DigestOut, "model" | "cost_usd" | "error">;
