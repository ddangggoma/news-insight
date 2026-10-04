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
