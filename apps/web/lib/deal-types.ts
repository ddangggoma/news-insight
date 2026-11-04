export type DealKind = "investment" | "acquisition" | "partnership" | "ipo" | "joint_venture" | "licensing";

export const DEAL_KIND_LABEL: Record<DealKind, string> = {
  investment: "투자",
  acquisition: "인수·합병",
  partnership: "제휴",
  ipo: "상장",
  joint_venture: "합작",
  licensing: "라이선스",
};

/** Colour by kind in charts and on cards: the four common kinds take categorical slots 1-4 in
 * this order (the order the palette was validated in); the rare ones share the neutral "기타". */
export const DEAL_SERIES = ["investment", "acquisition", "partnership", "ipo", "other"] as const;
export type DealSeries = (typeof DEAL_SERIES)[number];

export const DEAL_SERIES_LABEL: Record<DealSeries, string> = {
  investment: "투자",
  acquisition: "인수·합병",
  partnership: "제휴",
  ipo: "상장",
  other: "합작·라이선스",
};

export const DEAL_SERIES_COLOR: Record<DealSeries, string> = {
  investment: "var(--cat-1)",
  acquisition: "var(--cat-2)",
  partnership: "var(--cat-3)",
  ipo: "var(--cat-4)",
  other: "var(--cat-other)",
};

export function dealSeries(kind: DealKind): DealSeries {
  return kind === "joint_venture" || kind === "licensing" ? "other" : kind;
}

export interface DealParty {
  name: string;
  key: string | null;
  count: number;
  usd: number;
  kinds: Partial<Record<DealKind, number>>;
}

export interface DealStats {
  sized: number;
  usd: number;
  median_usd: number | null;
  mean_usd: number | null;
  max_usd: number | null;
  companies: number;
  pairs: number;
  /** Amounts of $50B or more: likely misreads (a valuation taken for the amount), left out of the sums. */
  outliers?: number;
}

export interface DealView {
  days: number;
  total: number;
  kinds: { kind: DealKind; count: number; usd: number; sized: number }[];
  months: { month: string; counts: Partial<Record<DealKind, number>> }[];
  /** Zero-filled weeks over the window, keyed by their Monday (absent from older APIs). */
  weeks?: { week: string; counts: Partial<Record<DealKind, number>>; usd: number }[];
  stats?: DealStats | null;
  parties: DealParty[];
  top_usd?: DealParty[];
  pairs: { actor: string; actor_key: string | null; counterparty: string; counterparty_key: string | null; count: number; kinds: DealKind[] }[];
  deals: {
    id: number;
    kind: DealKind;
    actor: string;
    actor_key: string | null;
    counterparty: string | null;
    counterparty_key: string | null;
    amount: number | null;
    currency: string | null;
    amount_usd: number | null;
    stage: string | null;
    announced_on: string | null;
    summary: string;
    item_id: number;
    title: string;
    source: string;
    url: string;
    reports: number;
    /** announced_on, or the evidence article's date when the deal names none. */
    occurred_on?: string | null;
    /** amount_usd of $50B or more: shown with a warning, never summed. */
    outlier?: boolean;
  }[];
}

export type Deal = DealView["deals"][number];

export interface DealBucket {
  key: string;
  label: string;
  total: number;
  usd: number | null;
  counts: Record<DealSeries, number>;
}

function emptyCounts(): Record<DealSeries, number> {
  return { investment: 0, acquisition: 0, partnership: 0, ipo: 0, other: 0 };
}

/** Deals per week (windows up to 90 days) or per month, stacked by kind series. */
export function dealBuckets(view: DealView): { unit: "week" | "month"; buckets: DealBucket[] } {
  const fold = (counts: Partial<Record<DealKind, number>>) => {
    const out = emptyCounts();
    for (const [kind, n] of Object.entries(counts)) out[dealSeries(kind as DealKind)] += n ?? 0;
    return out;
  };
  const total = (counts: Record<DealSeries, number>) => Object.values(counts).reduce((a, b) => a + b, 0);
  if (view.days <= 90 && view.weeks?.length) {
    return {
      unit: "week",
      buckets: view.weeks.map((w) => {
        const counts = fold(w.counts);
        return { key: w.week, label: `${Number(w.week.slice(5, 7))}.${Number(w.week.slice(8, 10))}`, total: total(counts), usd: w.usd, counts };
      }),
    };
  }
  return {
    unit: "month",
    buckets: view.months.map((m) => {
      const counts = fold(m.counts);
      return { key: m.month, label: `${m.month.slice(2, 4)}.${m.month.slice(5, 7)}`, total: total(counts), usd: null, counts };
    }),
  };
}

/** The amount in the currency the article gave: "3조 원", "5,000만 USD"; nothing for USD. */
export function formatOriginal(amount: number | null, currency: string | null): string {
  if (!amount || !currency || currency === "USD") return "";
  const compact = new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }).format(amount);
  return currency === "KRW" ? `${compact}원` : `${compact} ${currency}`;
}

/** A short dollar size for tiles and bars: "1.5억", "3,000만" (unit 달러 stated nearby). */
export function formatUsdShort(value: number | null | undefined): string {
  return value ? formatUsd(value).replace(/^약 /, "").replace(/ 달러$/, "") : "–";
}

/** A rough dollar size in Korean units: 약 1.5억 달러, 약 3,000만 달러. */
export function formatUsd(value: number | null | undefined): string {
  if (!value) return "";
  if (value >= 1e8) return `약 ${(value / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억 달러`;
  if (value >= 1e4) return `약 ${Math.round(value / 1e4).toLocaleString("ko-KR")}만 달러`;
  return `약 ${Math.round(value).toLocaleString("ko-KR")} 달러`;
}
