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
  signal_type: string | null;
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

export type Facets = Record<"field" | "theme" | "signal" | "impact" | "track" | "region" | "scope", Record<string, number>>;

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
  signal_types: Count[];
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
  /** Share of the current window already past; null for a closed window. */
  elapsed: number | null;
}

export type TopicKind = "field" | "theme" | "keyword";
export type TopicState = "new" | "surging" | "rising" | "steady" | "falling";
export type TrackMix = Record<Track, number>;

/** A field, theme or keyword: counts per window (oldest first) and current-window breakdowns. */
export interface Topic {
  key: string;
  label: string | null;
  field: string | null;
  counts: number[];
  change: number | null;
  z: number;
  state: TopicState | null;
  sources: number;
  tracks: TrackMix;
  previous_tracks: TrackMix;
  /** Summed over the windows before the current one. */
  baseline_tracks: TrackMix;
  impacts: Record<"opportunity" | "risk" | "watch", number>;
  /** Current window by source region. */
  regions: Record<Region, number>;
  /** Earliest report per region over the trend span (ISO time); regions without reports are absent. */
  first_seen: Partial<Record<Region, string>>;
  /** Current-window reports from official vendor sources. */
  official: number;
  /** 1 / HHI of reports per source: 1 = a single outlet. */
  effective_sources: number | null;
  /** Keywords only: first report ever, with the filters. */
  first_ever?: string | null;
  /** Keywords only: "new" in the span but reported before it. */
  returning?: boolean;
  /** Keywords only: first report ever within the last three windows. */
  debut?: boolean;
}

export interface KeywordPair {
  a: string;
  b: string;
  count: number;
  lift: number;
  is_new: boolean;
}

export interface FlowLink {
  source: Track;
  target: Track;
  count: number;
  median_hours: number;
}

export interface Radar {
  taxonomy_revised_on?: string | null;
  window: RadarWindow;
  periods: string[];
  kpis: {
    items: number[];
    stories: number[];
    sources: number[];
    research: number[];
    new_stories: number;
    cross_track_stories: number;
  };
  fields: Topic[];
  themes: Topic[];
  keywords: Topic[];
  pairs: KeywordPair[];
  /** Track-to-track hand-offs completed in the window. */
  flows: { chains: number; origins: Partial<Record<Track, number>>; links: FlowLink[]; ref_kinds?: Record<string, number> };
  engagement: Engagement;
  calendar: RadarCalendar;
  field_links: FieldLink[];
}

export interface EngagedItem {
  id: number;
  title: string;
  track: Track;
  source_name: string;
  metric: string;
  gain: number;
  current: number;
}

/** Reactions gained inside the window (stars, points, likes …). */
export interface Engagement {
  measured: number;
  themes: { key: string; score: number; items: number }[];
  top: EngagedItem[];
}

export interface Anomaly {
  day: string;
  field: string;
  count: number;
  expected: number;
  z: number;
  keywords: { key: string; label: string; count: number }[];
}

export interface RadarCalendar {
  start: string;
  days: number[];
  anomalies: Anomaly[];
}

export interface FieldLink {
  a: string;
  b: string;
  count: number;
  previous: number;
}

export interface TopicDetail {
  kind: TopicKind;
  topic: Topic;
  themes: Count[];
  keywords: { key: string; label: string; count: number }[];
  signal_types: Count[];
  regions: Count[];
  stories: ReaderItem[];
}

export type PublicDigest = Omit<DigestOut, "model" | "cost_usd" | "error">;
