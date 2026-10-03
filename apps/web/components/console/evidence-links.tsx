import type { DigestOut } from "@/lib/types";

export function EvidenceLinks({ ids, items }: { ids: number[]; items: DigestOut["items"] }) {
  const byId = new Map(items.map((item) => [item.id, item]));
  return (
    <span className="inline-flex flex-wrap gap-1 align-middle">
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
            className="rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            {item.source_name}
          </a>
        );
      })}
    </span>
  );
}
