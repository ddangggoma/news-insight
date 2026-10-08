// Mirrors apps/api/src/news_insight/public/schemas.py
import type { DigestOut, Region, Track } from "@/lib/types";

export interface StoryBrief {
  id: number;
  item_count: number;
  source_count: number;
  tracks: string[];
}

/** A registered company on a card (plan 12); relation is to Samsung DX. */
export interface CompanyRef {
  key: string;
  label: string;
  relation: CompanyRelation;
  kind: CompanyKind;
}

export type CompanyRelation = "self" | "competitor" | "supplier" | "partner" | "peer";
export type CompanyKind = "company" | "startup" | "institute" | "regulator" | "standards_body";

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
  companies?: CompanyRef[];
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

export type TopicKind = "field" | "theme" | "keyword" | "company";
export type TopicState = "new" | "surging" | "rising" | "steady" | "falling";
export type TrackMix = Record<Track, number>;

/** A field, theme or keyword: counts per window (oldest first) and current-window breakdowns. */
export interface Topic {
  key: string;
  label: string | null;
  field: string | null;
  counts: number[];
  /** Window in progress: every window counted up to the same elapsed share; change, z and state use these. */
  paced?: number[] | null;
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
  /** Rule-based cards computed by the API (public/signals.py), at most one per tone. */
  signals?: RadarSignal[];
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
  /** Registered companies reported with this topic in the window. */
  companies?: { key: string; label: string; count: number }[];
  /** kind=theme: the registry's major companies of the theme. */
  major_companies?: CompanyRef[];
  /** kind=company: the registry entry. */
  profile?: CompanyProfile | null;
}

export interface CompanyProfile {
  key: string;
  name: string;
  name_ko: string | null;
  kind: CompanyKind;
  region: string;
  relation: CompanyRelation;
  themes: string[];
}

export interface CompanyTopic extends Topic {
  name: string;
  name_ko: string | null;
  kind: CompanyKind;
  region: string;
  relation: CompanyRelation;
  /** Current-window reports from the company's own domains. */
  self_reports: number;
  signal_mix: Record<string, number>;
  baseline_mix: Record<string, number>;
  shift: { signal_type: string; share: number; baseline_share: number; z: number } | null;
  top_themes: Count[];
}

export interface ThemeLeaders {
  theme: string;
  total: number;
  previous_total: number;
  leaders: { key: string; label: string; count: number; share: number; previous_share: number | null }[];
  previous_leader: string | null;
  leader_changed: boolean;
}

export interface CompanyRadar {
  window: RadarWindow;
  periods: string[];
  /** Company-tagged reports per window. */
  tagged: number[];
  companies: CompanyTopic[];
  organizations: CompanyTopic[];
  theme_leaders: ThemeLeaders[];
  entries: { key: string; label: string; theme: string; count: number; sources: number }[];
  entrants: { key: string; name: string; registered: boolean; cards: number; sources: number; first_seen: string | null }[];
  pairs: { a: string; b: string; count: number; lift: number; is_new: boolean; signal_type: string | null }[];
  signals: RadarSignal[];
}

export type PublicDigest = Omit<DigestOut, "model" | "cost_usd" | "error">;

export interface RadarSignal {
  tone: string;
  title: string;
  detail: string;
  focus: { kind: "field" | "theme" | "keyword" | "company" | "search"; key: string };
  score: number;
}

/** Radar distribution over any scheme, depth and base node (plan 15-4b). */
export interface DistributionNode {
  key: string;
  label: string;
  depth: number;
  parent_key: string | null;
  count: number;
  previous: number;
  delta: number;
}

export interface Distribution {
  scheme: string;
  depth: number;
  root: DistributionNode | null;
  nodes: DistributionNode[];
  total: number;
  previous_total: number;
  schemes: { key: string; name: string; max_depth: number; level_names: string[] }[];
}
