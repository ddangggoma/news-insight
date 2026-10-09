import type { CompanyRef } from "@/lib/reader-types";

export type Stage = "research" | "organising" | "product" | "diffusion";

export const STAGE_LABEL: Record<Stage, string> = {
  research: "연구",
  organising: "표준·생태계",
  product: "제품",
  diffusion: "확산",
};

export const STAGE_HINT: Record<Stage, string> = {
  research: "논문·특허 신호가 많음",
  organising: "표준·생태계·규제 신호가 많음",
  product: "출시·보안 사건 신호가 많음",
  diffusion: "시장·투자·공급망 신호가 많음",
};

export interface AreaMaturity {
  key: string;
  label: string;
  field_key: string;
  field_label: string;
  count: number;
  mix: Record<Stage, number>;
  index: number;
  stage: Stage;
  history: { month: string; index: number | null; count: number }[];
  companies: CompanyRef[];
}

export interface MaturityView {
  days: number;
  fields: { key: string; label: string }[];
  areas: AreaMaturity[];
}

/** Index movement over the shown months: "+0.4" / "-0.2" / "". */
export function movement(history: AreaMaturity["history"]): string {
  const values = history.map((h) => h.index).filter((v): v is number => v != null);
  if (values.length < 2) return "";
  const diff = Math.round((values[values.length - 1] - values[0]) * 10) / 10;
  return diff === 0 ? "" : `${diff > 0 ? "+" : ""}${diff.toFixed(1)}`;
}
