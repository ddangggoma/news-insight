// Reader filter state lives in the URL: parse it leniently, serialise it in one fixed order.
import { REGION_LABEL, TRACK_LABEL } from "@/lib/format";
import type { QueryValue } from "@/lib/query";
import { withQuery } from "@/lib/query";
import type { SearchParams } from "@/lib/params";
import { COMPANY_KEY } from "@/lib/radar";
import { FIELD_LABEL, IMPACT_LABEL, SIGNAL_LABEL, THEME_LABEL } from "@/lib/taxonomy";

export const AXES = ["field", "theme", "signal", "impact", "track", "region"] as const;
export type Axis = (typeof AXES)[number];

export const AXIS_LABELS: Record<Axis, Record<string, string>> = {
  field: FIELD_LABEL,
  theme: THEME_LABEL,
  signal: SIGNAL_LABEL,
  impact: IMPACT_LABEL,
  track: TRACK_LABEL,
  region: REGION_LABEL,
};

export const SCOPES = { relevant: "DX 관련 + 의존 기술", dx: "DX 제품·기술만", all: "전체" } as const;
export const PERIODS = { "1d": "1일", "7d": "7일", "30d": "30일", all: "전체" } as const;
export const SORTS = { recent: "최신순", relevance: "관련도순", coverage: "보도 많은 순" } as const;

export type Scope = keyof typeof SCOPES;
export type Period = keyof typeof PERIODS;
export type Sort = keyof typeof SORTS;

export type ReaderFilters = Record<Axis, string[]> & {
  /** Registry company keys (plan 12): not a facet, set from company chips. */
  company: string[];
  scope: Scope;
  period: Period;
  sort: Sort;
  q: string;
  page: number;
};

const DEFAULTS = { scope: "relevant", period: "7d", sort: "recent", page: 1 } as const;

function values(params: SearchParams, name: string): string[] {
  const raw = params[name];
  return raw === undefined ? [] : Array.isArray(raw) ? raw : [raw];
}

function choice<T extends string>(raw: string | undefined, allowed: Record<T, string>, fallback: T): T {
  return raw !== undefined && raw in allowed ? (raw as T) : fallback;
}

export function parseReaderFilters(params: SearchParams): ReaderFilters {
  const axes = Object.fromEntries(
    AXES.map((axis) => [axis, [...new Set(values(params, axis).filter((v) => v in AXIS_LABELS[axis]))]]),
  ) as Record<Axis, string[]>;
  const page = Number.parseInt(values(params, "page")[0] ?? "1", 10);
  return {
    ...axes,
    company: [...new Set(values(params, "company").filter((v) => COMPANY_KEY.test(v)))],
    scope: choice(values(params, "scope")[0], SCOPES, DEFAULTS.scope),
    period: choice(values(params, "period")[0], PERIODS, DEFAULTS.period),
    sort: choice(values(params, "sort")[0], SORTS, DEFAULTS.sort),
    q: (values(params, "q")[0] ?? "").trim(),
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

/** Parameters for the reader API: every scalar explicit, empty axes left out. */
export function apiParams(filters: ReaderFilters): Record<string, QueryValue> {
  const params: Record<string, QueryValue> = {
    scope: filters.scope,
    period: filters.period,
    sort: filters.sort,
    page: filters.page,
  };
  for (const axis of AXES) if (filters[axis].length) params[axis] = filters[axis];
  if (filters.company.length) params.company = filters.company;
  if (filters.q) params.q = filters.q;
  return params;
}

function href(filters: ReaderFilters): string {
  return withQuery("/", {
    scope: filters.scope === DEFAULTS.scope ? undefined : filters.scope,
    period: filters.period === DEFAULTS.period ? undefined : filters.period,
    sort: filters.sort === DEFAULTS.sort ? undefined : filters.sort,
    ...Object.fromEntries(AXES.map((axis) => [axis, filters[axis]])),
    company: filters.company,
    q: filters.q || undefined,
    page: filters.page > 1 ? filters.page : undefined,
  });
}

export function pageHref(filters: ReaderFilters, page: number): string {
  return href({ ...filters, page });
}

export function toggleHref(filters: ReaderFilters, axis: Axis, key: string): string {
  const current = filters[axis];
  const next = current.includes(key) ? current.filter((v) => v !== key) : [...current, key];
  return href({ ...filters, [axis]: next, page: 1 });
}

export function removeHref(filters: ReaderFilters, axis: Axis | "q" | "company", key: string): string {
  if (axis === "q") return href({ ...filters, q: "", page: 1 });
  if (axis === "company") return href({ ...filters, company: filters.company.filter((v) => v !== key), page: 1 });
  return href({ ...filters, [axis]: filters[axis].filter((v) => v !== key), page: 1 });
}

export function setHref(filters: ReaderFilters, name: "scope" | "period" | "sort" | "q", value: string): string {
  return href({ ...filters, [name]: value, page: 1 } as ReaderFilters);
}

/** Drops every axis and the search, keeps scope, period and sort. */
export function clearHref(filters: ReaderFilters): string {
  const empty = Object.fromEntries(AXES.map((axis) => [axis, []])) as unknown as Record<Axis, string[]>;
  return href({ ...filters, ...empty, company: [], q: "", page: 1 });
}

export type Chip = { axis: Axis | "q" | "company"; key: string; label: string };

/** Feed link for one company (from a card's company chip). */
export function companyHref(key: string): string {
  return withQuery("/", { company: key });
}

/** `companies`: company key → display name, taken from the loaded cards. */
export function activeChips(filters: ReaderFilters, companies: Record<string, string> = {}): Chip[] {
  const chips: Chip[] = AXES.flatMap((axis) =>
    filters[axis].map((key) => ({ axis, key, label: AXIS_LABELS[axis][key] ?? key })),
  );
  for (const key of filters.company) chips.push({ axis: "company", key, label: `기업: ${companies[key] ?? key}` });
  if (filters.q) chips.push({ axis: "q", key: filters.q, label: `“${filters.q}”` });
  return chips;
}
