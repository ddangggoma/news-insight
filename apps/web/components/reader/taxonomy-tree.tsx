import Link from "next/link";

import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL, THEME_LABEL } from "@/lib/taxonomy";
import type { TaxonomyCounts } from "@/lib/reader-types";
import { cn } from "@/lib/utils";

export interface TopicSelection {
  field?: string;
  theme?: string;
  business?: string;
  impact?: string;
}

const themesOf = (field: string) => Object.keys(THEME_LABEL).filter((theme) => theme.startsWith(`${field}__`));

function NodeLink({ href, label, count, active }: { href: string; label: string; count?: number; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center justify-between gap-2 rounded-md px-2 py-1 text-sm hover:bg-muted",
        active && "bg-primary/10 font-medium text-primary",
      )}
    >
      <span className="truncate">{label}</span>
      {count ? <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{count}</span> : null}
    </Link>
  );
}

/** Wiki navigation (§9 left pane): 15 fields × 5 themes, DX businesses, impact. */
export function TaxonomyTree({ counts, selected = {} }: { counts: TaxonomyCounts; selected?: TopicSelection }) {
  const activeField = selected.field ?? selected.theme?.split("__")[0];
  return (
    <nav aria-label="주제 탐색" className="space-y-5 text-sm">
      <section className="space-y-1">
        <h2 className="px-2 text-xs font-semibold text-muted-foreground">DX 사업부</h2>
        {Object.entries(BUSINESS_LABEL).map(([key, label]) => (
          <NodeLink key={key} href={`/topics?business=${key}`} label={label} count={counts.businesses[key]} active={selected.business === key} />
        ))}
      </section>
      <section className="space-y-1">
        <h2 className="px-2 text-xs font-semibold text-muted-foreground">영향</h2>
        {Object.entries(IMPACT_LABEL).map(([key, label]) => (
          <NodeLink key={key} href={`/topics?impact=${key}`} label={label} count={counts.impacts[key]} active={selected.impact === key} />
        ))}
      </section>
      <section className="space-y-0.5">
        <h2 className="px-2 text-xs font-semibold text-muted-foreground">분야·테마</h2>
        {Object.entries(FIELD_LABEL).map(([field, label]) => (
          <details key={field} open={activeField === field} className="group/field">
            <summary className="flex cursor-pointer list-none items-center gap-1 rounded-md px-1 hover:bg-muted [&::-webkit-details-marker]:hidden">
              <span className="text-muted-foreground transition-transform group-open/field:rotate-90" aria-hidden>
                ›
              </span>
              <span className="min-w-0 flex-1">
                <NodeLink href={`/topics?field=${field}`} label={label} count={counts.fields[field]} active={selected.field === field} />
              </span>
            </summary>
            <div className="ml-4 border-l pl-1">
              {themesOf(field).map((theme) => (
                <NodeLink key={theme} href={`/topics?theme=${theme}`} label={THEME_LABEL[theme]} count={counts.themes[theme]} active={selected.theme === theme} />
              ))}
            </div>
          </details>
        ))}
      </section>
      <p className="px-2 text-xs text-muted-foreground">숫자는 최근 {counts.window_days}일 카드 수</p>
    </nav>
  );
}
