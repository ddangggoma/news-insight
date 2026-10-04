import Link from "next/link";

import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL, THEME_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

export const IMPACT_STYLE: Record<string, string> = {
  opportunity: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  risk: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  watch: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

export function shortLabel(key: string): string {
  return (BUSINESS_LABEL[key] ?? key).split(" · ")[0];
}

const chip = "rounded px-1.5 py-0.5 transition-colors hover:ring-1 hover:ring-current/30";

/** Classification chips that double as Wiki links (/topics). */
export function TopicChips({
  field,
  themes,
  businesses,
  impact,
}: {
  field: string | null;
  themes: string[];
  businesses: string[];
  impact: string | null;
}) {
  const theme = themes[0];
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      {businesses.map((business) => (
        <Link key={business} href={`/topics?business=${business}`} className={cn(chip, "bg-primary/10 font-medium text-primary")}>
          {shortLabel(business)}
        </Link>
      ))}
      {impact ? (
        <Link href={`/topics?impact=${impact}`} className={cn(chip, "font-medium", IMPACT_STYLE[impact])}>
          {IMPACT_LABEL[impact] ?? impact}
        </Link>
      ) : null}
      {theme ? (
        <Link href={`/topics?theme=${theme}`} className={cn(chip, "bg-muted text-muted-foreground")} title={FIELD_LABEL[field ?? ""]}>
          {THEME_LABEL[theme] ?? theme}
        </Link>
      ) : field ? (
        <Link href={`/topics?field=${field}`} className={cn(chip, "bg-muted text-muted-foreground")}>
          {FIELD_LABEL[field] ?? field}
        </Link>
      ) : null}
    </div>
  );
}
