import type { Stat } from "@/components/reader/insight-parts";
import { formatNumber } from "@/lib/format";
import { param, pageParam, type SearchParams } from "@/lib/params";
import type { CompanyKind, CompanyRelation } from "@/lib/reader-types";

/*
 * The 연구 (/research) and 특허 (/patents) menus (plan 19 §1): one response per tab from
 * /api/public/research and /api/public/patents (apps/api/src/news_insight/public/domains.py).
 * Windows are rolling and end yesterday (KST); `previous` is the same length just before.
 * Fields marked optional are newer than the first API version: read them defensively.
 */

export type DomainKind = "research" | "patent";
export type DomainTab = "overview" | "fields" | "companies" | "trends" | "documents";
export type DomainPeriod = "week" | "month" | "quarter";
export type Entity = "company" | "org";
export type TrendView = "chart" | "table";
export type Flag = "rise" | "fall";

export interface Span {
  start: string;
  /** Inclusive. */
  end: string;
}

export interface Option {
  key: string;
  label: string;
}

export interface InsightSentence {
  text: string;
  doc_ids: number[];
}

/** The daily Opus insight (plan 19 §3); null until one is published. */
export interface DomainInsight {
  date: string;
  sentences: InsightSentence[];
}

export interface WindowCount {
  key: string;
  label: string;
  count: number;
  previous: number;
  /** (count - previous) / previous; null when previous is 0. */
  change: number | null;
}

export interface Riser {
  key: string;
  label: string;
  count: number;
  /** Mean of the previous windows. */
  mean: number;
  ratio: number | null;
  z: number;
}

export interface Kpis {
  count: number;
  previous: number;
  change: number | null;
  rising_field: Riser | null;
  company_share: number | null;
  company_docs: number;
  watched_count: number;
  watched_previous: number;
}

export interface HeatmapRow {
  key: string;
  label: string;
  /** One per week, oldest first. */
  counts: number[];
}

export interface Heatmap {
  weeks: Span[];
  rows: HeatmapRow[];
  max: number;
}

export interface OverviewTab {
  /** Why some flags or KPIs are held back (short history, enrichment coverage). */
  coverage_note?: string | null;
  kpis: Kpis;
  heatmap: Heatmap;
  risers: Riser[];
  insight?: DomainInsight | null;
}

export interface CompanyOut {
  key: string;
  label: string;
  relation: CompanyRelation | string;
  kind: CompanyKind | string;
  watched: boolean;
}

export interface OrgCount {
  name: string;
  org_type: string;
  count: number;
  previous: number;
  change: number | null;
}

export interface Doc {
  id: number;
  url: string;
  title: string;
  title_ko: string | null;
  summary: string | null;
  source_name: string;
  occurred_at: string;
  field: string;
  field_label: string;
  companies: CompanyOut[];
  watched: boolean;
  score: number;
  // research
  venue?: string | null;
  orgs?: string[];
  cited_by?: number | null;
  mentions?: number;
  upvotes?: number | null;
  // patents
  publication_number?: string | null;
  office?: string | null;
  patent_source?: string | null;
  applicants?: string[];
  press?: number;
}

export interface RankedCompany {
  /** Registry key, or the institution name for an org. */
  key: string;
  label: string;
  entity: Entity;
  relation: string | null;
  kind: string | null;
  org_type: string | null;
  watched: boolean;
  count: number;
  previous: number;
  change: number | null;
  top_fields: WindowCount[];
}

export interface FieldDetail {
  key: string;
  label: string;
  count: number;
  previous: number;
  change: number | null;
  themes: WindowCount[];
  /** Per trend window (FieldsTab.buckets). */
  series: number[];
  companies: RankedCompany[];
  orgs: OrgCount[];
  documents: Doc[];
  insight?: DomainInsight | null;
}

export interface FieldsTab {
  items: WindowCount[];
  other: WindowCount;
  selected: string;
  buckets: Span[];
  detail: FieldDetail;
}

export interface WatchedCompany {
  company: CompanyOut;
  count: number;
  previous: number;
  change: number | null;
  fields: WindowCount[];
  series: number[];
}

export interface WatchBlock {
  buckets: Span[];
  /** Watched companies in the registry. */
  total: number;
  companies: WatchedCompany[];
}

export interface CompanyDetail {
  key: string;
  label: string;
  entity: Entity;
  relation: string | null;
  org_type: string | null;
  watched: boolean;
  count: number;
  previous: number;
  change: number | null;
  fields: WindowCount[];
  series: number[];
  /** 최근 문헌: the 10 most recent of the window. */
  documents: Doc[];
  /** The 10 best scored of the window. */
  top_documents?: Doc[] | null;
}

export interface CompaniesTab {
  kind: Entity;
  ranking: RankedCompany[];
  watch: WatchBlock;
  detail: CompanyDetail | null;
  insight?: DomainInsight | null;
}

export interface Series {
  key: string;
  label: string;
  counts: number[];
  current: number;
  mean: number;
  z: number;
  flag: Flag | null;
}

export interface FlagOut {
  axis: "field" | "country" | "office";
  key: string;
  label: string;
  flag: Flag;
  z: number;
  current: number;
  mean: number;
}

export interface TrendsTab {
  /** Why some rise/fall flags are held back. */
  coverage_note?: string | null;
  buckets: Span[];
  history: number;
  fields: Series[];
  regions_axis: "country" | "office";
  regions: Series[];
  flags: FlagOut[];
}

export interface DocumentsTab {
  page: number;
  size: number;
  total: number;
  items: Doc[];
}

export interface Coverage {
  news: number;
  eps: number;
  ops: number;
  note: string;
}

export interface DomainView {
  kind: DomainKind;
  tab: DomainTab;
  period: DomainPeriod;
  /** The last day counted (yesterday, KST). */
  as_of: string;
  window: Span;
  previous: Span;
  field: string | null;
  company: string | null;
  org: string | null;
  field_options: Option[];
  coverage?: Coverage | null;
  /** A note on what the counts leave out (newer API). */
  coverage_note?: string | null;
  overview?: OverviewTab | null;
  fields?: FieldsTab | null;
  companies?: CompaniesTab | null;
  trends?: TrendsTab | null;
  documents?: DocumentsTab | null;
}

// ── menus, tabs, periods ─────────────────────────────────────────────────────────────────

export const DOMAIN_META: Record<DomainKind, { path: string; api: string; title: string; noun: string; intro: string }> = {
  research: {
    path: "/research",
    api: "/research",
    title: "연구",
    noun: "논문",
    intro: "논문을 기술분야·기업·대학과 연구기관·국가별로 세고, 직전 기간과 비교해 늘어나는 곳을 찾습니다.",
  },
  patent: {
    path: "/patents",
    api: "/patents",
    title: "특허",
    noun: "특허",
    intro: "특허 문헌을 기술분야·출원 기업·공개국별로 세고, 직전 기간과 비교해 늘어나는 곳을 찾습니다.",
  },
};

export const DOMAIN_TABS: readonly { key: DomainTab; label: string }[] = [
  { key: "overview", label: "개요" },
  { key: "fields", label: "기술분야별" },
  { key: "companies", label: "기업·기관별" },
  { key: "trends", label: "추이" },
  { key: "documents", label: "주목 문헌" },
];

export const PERIODS: readonly { key: DomainPeriod; label: string; unit: string; days: number }[] = [
  { key: "week", label: "1주", unit: "주", days: 7 },
  { key: "month", label: "1개월", unit: "30일", days: 30 },
  { key: "quarter", label: "분기", unit: "90일", days: 90 },
];

export const ENTITY_LABEL: Record<Entity, string> = { company: "기업", org: "대학·연구기관" };

/** OpenAlex institution types. */
const ORG_TYPE_LABEL: Record<string, string> = {
  education: "대학",
  facility: "연구시설",
  government: "정부기관",
  company: "기업",
  healthcare: "의료기관",
  nonprofit: "비영리",
  funder: "연구재단",
  archive: "아카이브",
  other: "기관",
};

export function orgTypeLabel(type: string | null | undefined): string {
  return type ? (ORG_TYPE_LABEL[type] ?? type) : "";
}

export const OTHER_FIELD = "other";

export interface DomainState {
  tab: DomainTab;
  period: DomainPeriod;
  field: string | null;
  company: string | null;
  org: string | null;
  kind: Entity;
  page: number;
  view: TrendView;
}

const isTab = (value: string | undefined): value is DomainTab => DOMAIN_TABS.some((t) => t.key === value);
const isPeriod = (value: string | undefined): value is DomainPeriod => PERIODS.some((p) => p.key === value);

/** The page's state from its address; unknown values fall back to the defaults. */
export function parseDomainState(domain: DomainKind, sp: SearchParams): DomainState {
  const tab = param(sp, "tab");
  const period = param(sp, "period");
  const research = domain === "research";
  return {
    tab: isTab(tab) ? tab : "overview",
    period: isPeriod(period) ? period : "month",
    field: param(sp, "field")?.slice(0, 40) ?? null,
    company: param(sp, "company")?.slice(0, 80) ?? null,
    org: research ? (param(sp, "org")?.slice(0, 200) ?? null) : null,
    kind: research && param(sp, "kind") === "org" ? "org" : "company",
    page: Math.min(pageParam(sp), 100),
    view: param(sp, "view") === "table" ? "table" : "chart",
  };
}

/** The API query for a state (only what the tab reads). */
export function domainQuery(domain: DomainKind, state: DomainState): Record<string, string | number | undefined> {
  const query: Record<string, string | number | undefined> = { tab: state.tab, period: state.period };
  if (state.field && state.tab !== "overview") query.field = state.field;
  if (state.tab === "companies" || state.tab === "documents") {
    if (state.company) query.company = state.company;
    if (domain === "research" && state.org) query.org = state.org;
  }
  if (domain === "research" && state.tab === "companies" && state.kind === "org") query.kind = "org";
  if (state.tab === "documents" && state.page > 1) query.page = state.page;
  return query;
}

/** The address of `state` with `patch` applied; defaults are left out. */
export function domainHref(domain: DomainKind, state: DomainState, patch: Partial<DomainState> = {}): string {
  const next = { ...state, ...patch };
  const params = new URLSearchParams();
  if (next.tab !== "overview") params.set("tab", next.tab);
  if (next.period !== "month") params.set("period", next.period);
  if (next.field) params.set("field", next.field);
  if (domain === "research" && next.kind === "org") params.set("kind", "org");
  if (next.company) params.set("company", next.company);
  if (domain === "research" && next.org) params.set("org", next.org);
  if (next.view === "table") params.set("view", "table");
  if (next.page > 1) params.set("page", String(next.page));
  const query = params.toString();
  return `${DOMAIN_META[domain].path}${query ? `?${query}` : ""}`;
}

/** Another tab: the period and field stay, the selection, page and table view do not. */
export function tabHref(domain: DomainKind, state: DomainState, tab: DomainTab): string {
  return domainHref(domain, state, { tab, company: null, org: null, kind: "company", page: 1, view: "chart" });
}

// ── numbers ──────────────────────────────────────────────────────────────────────────────

/** "▲25%", "▼10%", "±0%"; "새로" from nothing; "–" when there is nothing either side. */
export function changeText(change: number | null, count: number, previous: number): string {
  if (change === null || previous === 0) return count > 0 ? "새로" : "–";
  const percent = Math.round(change * 100);
  if (percent === 0) return "±0%";
  return `${percent > 0 ? "▲" : "▼"}${Math.abs(percent)}%`;
}

export function changeTone(change: number | null, count: number, previous: number): "up" | "down" | "flat" | "new" {
  if (previous === 0) return count > 0 ? "new" : "flat";
  if (change === null || Math.round(change * 100) === 0) return "flat";
  return change > 0 ? "up" : "down";
}

/** "2026-10-27" → "10/27". */
export function shortDay(day: string): string {
  return `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}`;
}

/** "10/5–11/3". */
export function spanLabel(span: Span): string {
  return `${shortDay(span.start)}–${shortDay(span.end)}`;
}

export function periodMeta(period: DomainPeriod) {
  return PERIODS.find((p) => p.key === period)!;
}

/** The four headline tiles of 개요. */
export function kpiStats(view: DomainView, kpis: Kpis): Stat[] {
  const noun = DOMAIN_META[view.kind].noun;
  const vs = `직전 ${spanLabel(view.previous)}`;
  const rising = kpis.rising_field;
  return [
    {
      label: `이번 기간 ${noun}`,
      value: formatNumber(kpis.count),
      unit: "건",
      note: `${vs} ${formatNumber(kpis.previous)}건 · ${changeText(kpis.change, kpis.count, kpis.previous)}`,
    },
    {
      label: "급증 분야",
      value: rising ? rising.label : "–",
      note: rising
        ? `${formatNumber(rising.count)}건, 이전 4개 기간 평균 ${formatNumber(Math.round(rising.mean * 10) / 10)}건${rising.ratio ? ` (×${rising.ratio.toFixed(1)})` : ""}`
        : "이전 기간보다 늘어난 분야 없음",
    },
    {
      label: view.kind === "research" ? "기업 저자 비중" : "기업 출원 비중",
      value: kpis.company_share === null ? "–" : String(Math.round(kpis.company_share * 100)),
      unit: kpis.company_share === null ? undefined : "%",
      note: `기업이 참여한 ${noun} ${formatNumber(kpis.company_docs)}건`,
    },
    {
      label: `관심 기업 ${noun}`,
      value: formatNumber(kpis.watched_count),
      unit: "건",
      note: `${vs} ${formatNumber(kpis.watched_previous)}건 · ${changeText(
        kpis.watched_previous ? (kpis.watched_count - kpis.watched_previous) / kpis.watched_previous : null,
        kpis.watched_count,
        kpis.watched_previous,
      )}`,
    },
  ];
}

/** Heat level 0-88 of a count against the map's peak (0 stays blank). */
export function heatLevel(count: number, max: number): number {
  if (!count || max <= 0) return 0;
  return Math.max(10, Math.round((count / max) * 88));
}

/** A company detail's best-scored documents of the window. */
export function topDocs(detail: CompanyDetail): Doc[] {
  return detail.top_documents ?? [];
}

/** A company detail's most recent documents of the window (shown only next to a scored list). */
export function recentDocs(detail: CompanyDetail): Doc[] {
  return detail.top_documents ? detail.documents : [];
}

/** Series colours: categorical slots 1-8, then the 기타 grey. */
export function seriesColor(index: number, key?: string): string {
  if (key === "rest" || key === OTHER_FIELD) return "var(--cat-other)";
  return `var(--cat-${(index % 8) + 1})`;
}
