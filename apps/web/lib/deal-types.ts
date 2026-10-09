export type DealKind = "investment" | "acquisition" | "partnership" | "ipo" | "joint_venture" | "licensing";

export const DEAL_KIND_LABEL: Record<DealKind, string> = {
  investment: "투자",
  acquisition: "인수·합병",
  partnership: "제휴",
  ipo: "상장",
  joint_venture: "합작",
  licensing: "라이선스",
};

export interface DealView {
  days: number;
  total: number;
  kinds: { kind: DealKind; count: number; usd: number; sized: number }[];
  months: { month: string; counts: Partial<Record<DealKind, number>> }[];
  parties: { name: string; key: string | null; count: number; usd: number; kinds: Partial<Record<DealKind, number>> }[];
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
  }[];
}

/** A rough dollar size in Korean units: 약 1.5억 달러, 약 3,000만 달러. */
export function formatUsd(value: number | null | undefined): string {
  if (!value) return "";
  if (value >= 1e8) return `약 ${(value / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억 달러`;
  if (value >= 1e4) return `약 ${Math.round(value / 1e4).toLocaleString("ko-KR")}만 달러`;
  return `약 ${Math.round(value).toLocaleString("ko-KR")} 달러`;
}
