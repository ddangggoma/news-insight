// Company registry labels (plan 12). Relation is to Samsung DX.
import type { CompanyKind, CompanyRelation } from "@/lib/reader-types";

export const RELATION_META: Record<CompanyRelation, { label: string; color: string }> = {
  self: { label: "삼성", color: "var(--primary)" },
  competitor: { label: "경쟁", color: "var(--impact-risk)" },
  supplier: { label: "공급", color: "var(--viz-news)" },
  partner: { label: "협력", color: "var(--impact-opportunity)" },
  peer: { label: "기타", color: "var(--muted-foreground)" },
};

export const COMPANY_KIND_LABEL: Record<CompanyKind, string> = {
  company: "기업",
  startup: "스타트업",
  institute: "연구기관",
  regulator: "규제·정부",
  standards_body: "표준·업계 단체",
};

export const COMPANY_REGION_LABEL: Record<string, string> = {
  kr: "한국",
  us: "미국",
  cn: "중국",
  jp: "일본",
  tw: "대만",
  eu: "유럽",
  other: "기타",
};

/** Company radar card tones (API public/companies.py). */
export const COMPANY_SIGNAL_LABEL: Record<string, string> = {
  company_surge: "기업 급부상",
  company_shift: "기업 활동 전환",
  theme_entry: "새 테마 진입",
  new_entrant: "신흥 업체",
};
