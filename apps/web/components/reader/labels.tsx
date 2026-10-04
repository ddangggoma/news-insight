import { cn } from "@/lib/utils";
import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL } from "@/lib/taxonomy";

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

/** "MX · 모바일·온디바이스 AI" → "MX" for compact tags; the full name goes in the title. */
export function BusinessTag({ business }: { business: string }) {
  const label = BUSINESS_LABEL[business] ?? business;
  return (
    <span
      title={label}
      className="rounded-md border border-dashed px-2 py-px text-xs font-medium whitespace-nowrap text-ink-2"
    >
      {label.split(" · ")[0]}
    </span>
  );
}
