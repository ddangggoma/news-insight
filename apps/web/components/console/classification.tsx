import { cn } from "@/lib/utils";
import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL, SCOPE_LABEL, THEME_LABEL } from "@/lib/taxonomy";
import type { CardBody } from "@/lib/types";

const IMPACT_STYLE: Record<string, string> = {
  opportunity: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  risk: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  watch: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

export function shortBusiness(key: string): string {
  return (BUSINESS_LABEL[key] ?? key).split(" · ")[0];
}

/** Compact classification row: DX businesses, impact, theme; irrelevant/excluded are flagged. */
export function ClassificationBadges({ card, showTheme = true }: { card: CardBody; showTheme?: boolean }) {
  const scope = card.scope ?? null;
  if (!card.field && !scope) return null;
  const theme = card.themes?.[0];
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      {(card.businesses ?? []).map((business) => (
        <span key={business} className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">
          {shortBusiness(business)}
        </span>
      ))}
      {card.impact ? (
        <span className={cn("rounded px-1.5 py-0.5 font-medium", IMPACT_STYLE[card.impact])}>
          {IMPACT_LABEL[card.impact] ?? card.impact}
        </span>
      ) : null}
      {showTheme && theme ? (
        <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground" title={FIELD_LABEL[card.field ?? ""]}>
          {THEME_LABEL[theme] ?? theme}
        </span>
      ) : null}
      {scope === "irrelevant" || scope === "excluded" ? (
        <span className="rounded border border-dashed px-1.5 py-0.5 text-muted-foreground">{SCOPE_LABEL[scope]}</span>
      ) : null}
      {typeof card.relevance === "number" ? (
        <span className="ml-auto text-muted-foreground tabular-nums" title="DX 관련도 (0~100)">
          관련도 {card.relevance}
        </span>
      ) : null}
    </div>
  );
}
