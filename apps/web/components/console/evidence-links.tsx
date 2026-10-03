import { ExternalLink } from "lucide-react";

import type { DigestOut } from "@/lib/types";

export function EvidenceLinks({ ids, items }: { ids: number[]; items: DigestOut["items"] }) {
  const byId = new Map(items.map((item) => [item.id, item]));
  return (
    <span className="flex flex-wrap gap-1.5">
      {ids.map((id) => {
        const item = byId.get(id);
        if (!item) return null;
        return (
          <a
            key={id}
            href={item.url}
            target="_blank"
            rel="noreferrer"
            title={item.title}
            className="group inline-flex max-w-full items-center gap-1 rounded-md border bg-background px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground sm:max-w-72"
          >
            <span className="shrink-0 font-medium text-foreground/80">{item.source_name}</span>
            <span className="truncate">{item.title}</span>
            <ExternalLink className="size-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
          </a>
        );
      })}
    </span>
  );
}
