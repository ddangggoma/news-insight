import { EvidenceLinks } from "@/components/console/evidence-links";
import type { BriefingPersona, PublicBriefing } from "@/lib/briefing-types";
import { cn } from "@/lib/utils";

/** One role's reading of the day: headline first, the insight, actions and evidence on open. */
export function PersonaCard({
  persona,
  refs,
  open = false,
  className,
}: {
  persona: BriefingPersona;
  refs: PublicBriefing["refs"];
  open?: boolean;
  className?: string;
}) {
  return (
    <details open={open} className={cn("group/persona rounded-lg border p-3 open:bg-muted/30", className)}>
      <summary className="cursor-pointer list-none space-y-1 [&::-webkit-details-marker]:hidden">
        <p className="flex items-center justify-between gap-2 text-xs font-medium text-primary">
          {persona.name}
          {persona.relevance ? <span className="text-muted-foreground tabular-nums">관련도 {persona.relevance}</span> : null}
        </p>
        <p className="text-sm leading-snug font-semibold">{persona.headline}</p>
      </summary>
      <div className="mt-2 space-y-2 text-sm">
        <p className="leading-relaxed text-foreground/85">{persona.insight}</p>
        {persona.actions.length > 0 ? (
          <ul className="list-disc space-y-0.5 pl-4 text-foreground/80">
            {persona.actions.map((action, index) => (
              <li key={index}>{action}</li>
            ))}
          </ul>
        ) : null}
        <EvidenceLinks ids={persona.item_ids} items={refs} />
      </div>
    </details>
  );
}
