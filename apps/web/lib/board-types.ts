export type Impact = "opportunity" | "risk" | "watch";
export type Horizon = "1y" | "3y" | "5y";

export const IMPACT_TEXT: Record<Impact, string> = { opportunity: "기회", risk: "위험", watch: "관찰" };
export const HORIZON_TEXT: Record<Horizon, string> = { "1y": "1년", "3y": "3년", "5y": "5년" };

export interface BoardClaim {
  text: string;
  kind: "roadmap" | "opportunity" | "risk";
  horizon: Horizon | null;
  briefing_date: string;
  item_ids: number[];
}

export interface BoardRow {
  key: string;
  label: string;
  field_label: string;
  counts: Record<Impact, number>;
  evidence: Record<Impact, { item_id: number; title: string; first_seen_at: string }[]>;
  horizons: Record<Horizon, BoardClaim[]>;
  claims: BoardClaim[];
  persona: { stances: Partial<Record<Impact, number>>; headlines: string[] } | null;
}

export interface BoardView {
  days: number;
  persona: string | null;
  personas: { key: string; name: string; group: string }[];
  rows: BoardRow[];
}

/** Share of opportunity among opportunity + risk, 0-100 (50 when neither). */
export function opportunityShare(counts: Record<Impact, number>): number {
  const total = counts.opportunity + counts.risk;
  return total ? Math.round((counts.opportunity / total) * 100) : 50;
}
