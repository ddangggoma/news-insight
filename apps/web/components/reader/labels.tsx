import Link from "next/link";

import { RELATION_META } from "@/lib/companies";
import { companyHref } from "@/lib/reader-filters";
import type { CompanyRef } from "@/lib/reader-types";
import { cn } from "@/lib/utils";
import { FIELD_LABEL, IMPACT_LABEL, SIGNAL_LABEL } from "@/lib/taxonomy";

const IMPACT_CLASS: Record<string, string> = {
  opportunity: "bg-impact-opportunity/12 text-impact-opportunity",
  risk: "bg-impact-risk/12 text-impact-risk",
  watch: "bg-muted text-impact-watch",
};

export function ImpactBadge({ impact }: { impact: string | null }) {
  if (!impact) return null;
  return (
    <span className={cn("rounded-full px-2 py-px text-xs font-semibold whitespace-nowrap", IMPACT_CLASS[impact])}>
      {IMPACT_LABEL[impact] ?? impact}
    </span>
  );
}

export function FieldTag({ field }: { field: string | null }) {
  if (!field) return null;
  return (
    <span className="rounded-md border bg-muted px-2 py-px text-xs font-medium whitespace-nowrap text-ink-2">
      {FIELD_LABEL[field] ?? field}
    </span>
  );
}

/** Kind of news (research, launch, regulation, …): taxonomy v2 signal type. */
export function SignalTag({ signal }: { signal: string | null }) {
  if (!signal) return null;
  return (
    <span className="rounded-md border border-dashed px-2 py-px text-xs font-medium whitespace-nowrap text-ink-2">
      {SIGNAL_LABEL[signal] ?? signal}
    </span>
  );
}

/** Registered companies on a card (plan 12): each opens the feed for that company. */
export function CompanyChips({ companies, max = 4 }: { companies?: CompanyRef[]; max?: number }) {
  if (!companies?.length) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="관련 기업">
      {companies.slice(0, max).map((company) => (
        <li key={company.key}>
          <Link
            href={companyHref(company.key)}
            className="inline-flex items-center gap-1 rounded-full border px-2 py-px text-[11px] text-ink-2 transition hover:border-primary hover:text-primary"
            title={`${RELATION_META[company.relation].label} · 이 기업 기사 모두 보기`}
          >
            <span aria-hidden className="size-1.5 rounded-full" style={{ background: RELATION_META[company.relation].color }} />
            {company.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}
