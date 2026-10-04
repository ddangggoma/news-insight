export type Track = "news" | "community" | "research_ip" | "oss";
export type Region = "kr" | "global_en" | "jp" | "greater_china" | "eu_other";
export type Stage = "unverified" | "V0" | "V1" | "V2" | "V3" | "V4" | "V5" | "V6";
export type SourceStatus = "candidate" | "active" | "paused" | "retired";
export type Outcome = "success" | "not_modified" | "failed" | "dead_lettered" | "skipped";
export type DigestStatus = "published" | "fallback";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface Overview {
  generated_at: string;
  tracks: { track: Track; total: number; active: number; target: number }[];
  regions: { region: Region; total: number; active: number; capacity: number }[];
  stages: { stage: Stage; count: number }[];
  health: {
    window_hours: number;
    runs: number;
    success: number;
    not_modified: number;
    failed: number;
    dead_lettered: number;
    skipped: number;
    items_new: number;
    paused_sources: number;
    open_dead_letters: number;
  };
}

export interface SourceRow {
  key: string;
  name: string;
  track: Track;
  category: string;
  region: Region;
  access_method: string;
  validation_stage: Stage;
  status: SourceStatus;
  paused_reason: string | null;
  next_due_at: string | null;
  interval_seconds: number | null;
  consecutive_failures: number;
  last_success_at: string | null;
  items_total: number;
}

export interface RunOut {
  id: number;
  source_key: string;
  started_at: string;
  outcome: Outcome;
  http_status: number | null;
  elapsed_ms: number | null;
  items_new: number;
  items_updated: number;
  items_unchanged: number;
  error_code: string | null;
  error_message: string | null;
  canary: boolean;
}

export interface ItemRow {
  id: number;
  title: string;
  url: string;
  source_key: string;
  source_name: string;
  track: Track;
  category: string;
  region: Region;
  published_at: string | null;
  first_seen_at: string;
  revision: number;
  canary: boolean;
  metrics: Record<string, number>;
  title_ko: string | null;
}

export interface CardBody {
  title_ko: string | null;
  summary_ko: string[];
  keywords: string[];
  status: "ready" | "failed";
  engine: string | null;
  model: string | null;
  generated_at: string;
  field?: string | null;
  themes?: string[];
  signal_type?: string | null;
  impact?: string | null;
  scope?: string | null;
  relevance?: number | null;
}

export interface StoryRef {
  id: number;
  item_count: number;
  source_count: number;
  tracks: string[];
  is_representative: boolean;
}

export interface CardView {
  item: ItemRow;
  card: CardBody;
  story?: StoryRef | null;
}

export interface StoryMember {
  item: ItemRow;
  relation: "seed" | "exact" | "near" | "event";
  similarity: number | null;
}

export interface StoryView {
  id: number;
  title_ko: string | null;
  item_count: number;
  source_count: number;
  tracks: Track[];
  first_seen_at: string;
  last_seen_at: string;
  max_relevance: number | null;
  representative: ItemRow;
  card: CardBody | null;
  members: StoryMember[];
}

export interface SignalChain {
  kind: "arxiv" | "doi" | "github";
  value: string;
  tracks: Track[];
  items: ItemRow[];
}

export interface CardStats {
  ready: number;
  failed: number;
  pending: number;
  reclassify?: number;
  ready_today: number;
  success_rate_7d?: number | null;
  scope_7d?: Record<string, number>;
  by_engine: Record<string, number>;
  last_run: {
    started_at: string;
    finished_at: string | null;
    ready: number;
    failed: number;
    batches: Record<string, number>;
    quota: { weekly?: number | null; five_hour?: number | null };
    note: string | null;
  } | null;
}

export interface SourceDetail {
  source: SourceRow;
  endpoint_url: string;
  official_domain: string;
  operator: string;
  language: string;
  poll_class: string;
  dx_relevance: string;
  terms_url: string | null;
  storage_right: string | null;
  config: Record<string, unknown>;
  events: { stage: Stage; outcome: "passed" | "failed" | "reset"; reasons: string[]; created_at: string }[];
  runs: RunOut[];
  items: ItemRow[];
}

export interface DeadLetterOut {
  id: number;
  source_key: string;
  error_code: string;
  error_message: string;
  attempts: number;
  created_at: string;
  resolved_at: string | null;
  resolution: string | null;
}

export interface ItemDetail {
  item: ItemRow;
  summary: string | null;
  body: string | null;
  author: string | null;
  revisions: { revision: number; title: string; recorded_at: string }[];
  metric_history: { captured_at: string; metrics: Record<string, number> }[];
  card: CardBody | null;
}

export interface MoverOut {
  item: ItemRow;
  current: number;
  baseline: number;
  delta: number;
}

export interface DigestPoint {
  text: string;
  item_ids: number[];
}

export interface DigestOut {
  digest_date: string;
  version: number;
  status: DigestStatus;
  model: string | null;
  generated_at: string;
  window_start: string;
  window_end: string;
  item_count: number;
  cost_usd: number | null;
  error: string | null;
  content: {
    headline: string;
    overview: string;
    tracks: {
      track: Track;
      summary: string;
      categories: { category: string; headline: string; points: DigestPoint[] }[];
    }[];
    insights: { title: string; body: string; item_ids: number[] }[];
  };
  items: { id: number; title: string; url: string; source_name: string; track: Track }[];
}

export interface DigestSummary {
  digest_date: string;
  version: number;
  status: DigestStatus;
  headline: string;
  item_count: number;
  generated_at: string;
}

export type Verdict = "relevant" | "irrelevant" | "unsure";

export interface ReviewOut {
  verdict: Verdict;
  note: string | null;
  reviewed_at: string;
}

export interface ReviewItem {
  item: ItemRow;
  card: CardBody | null;
  review: ReviewOut | null;
}

export interface ReviewSample {
  seed: string;
  items: ReviewItem[];
  reviewed: number;
}

export interface ReviewBucket {
  key: string;
  total: number;
  relevant: number;
  irrelevant: number;
  unsure: number;
}

export interface ReviewStats {
  classifier: {
    tp: number;
    fp: number;
    fn: number;
    tn: number;
    precision: number | null;
    recall: number | null;
    accuracy: number | null;
  };
  overall: ReviewBucket;
  by_track: ReviewBucket[];
  by_category: ReviewBucket[];
  worst_sources: ReviewBucket[];
}

export interface CardFailure {
  item: ItemRow;
  error: string | null;
  attempts: number;
  generated_at: string;
}

export interface SourceQualityRow {
  key: string;
  name: string;
  track: Track;
  category: string;
  region: Region;
  validation_stage: Stage;
  status: SourceStatus;
  paused_reason: string | null;
  items_7d: number;
  classified_7d: number;
  relevance: number | null;
  translation: number | null;
}

export interface GateOut {
  name: string;
  label: string;
  value: number;
  threshold: number;
  passed: boolean;
  blocking: boolean;
}

export interface BriefingOut {
  briefing_date: string;
  version: number;
  status: "published" | "blocked";
  published_at: string;
  frozen_at: string;
  candidates: number;
  gates: GateOut[];
  failing: string[];
  sections: { track: Track; items: CardView[] }[];
  digest: DigestOut | null;
  strategy?: StrategyOut | null;
  is_current: boolean;
  current_date: string | null;
}

export interface BriefingSummary {
  briefing_date: string;
  version: number;
  status: "published" | "blocked";
  shortlist: number;
  failing: string[];
  published_at: string;
}

export interface StrategyClaim {
  id: string;
  text: string;
  item_ids: number[];
  horizon?: "1y" | "3y" | "5y";
}

export interface StrategyOut {
  status: "ok" | "failed";
  personas: {
    key: string;
    name: string;
    group: "executive" | "business" | "domain";
    status: "insight" | "no_signal";
    headline: string;
    insight: string;
    actions: string[];
    item_ids: number[];
  }[];
  report: {
    summary: string;
    fields: { field: string; summary: string; claims: StrategyClaim[] }[];
    roadmap: StrategyClaim[];
    opportunities: StrategyClaim[];
    risks: StrategyClaim[];
  } | null;
  review: { verdict: "pass" | "revise"; issues: { claim_id: string; kind: string; note: string }[] } | null;
  dropped_claims: number;
  error: string | null;
  cost_usd: number | null;
  items: DigestOut["items"];
}

export interface AlertOut {
  id: number;
  key: string;
  severity: "critical" | "warning" | "info";
  title: string;
  detail: string;
  opened_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  notified_at: string | null;
}

export interface TopicCandidate {
  key: string;
  label: string;
  count: number;
  recent: number;
  first_seen: string;
  last_seen: string;
  fields: Record<string, number>;
  examples: ItemRow[];
}

export interface TechnologyOut {
  key: string;
  label: string;
  theme_key: string | null;
  kind: "technology" | "standard" | "regulation" | "product_family";
  status: "active" | "watch" | "ignored";
  aliases: string[];
  cards_30d: number;
  edited_in_console: boolean;
}

export interface TechnologyCandidate {
  key: string;
  label: string;
  count: number;
}
