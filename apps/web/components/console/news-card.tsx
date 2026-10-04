import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { TrackBadge } from "@/components/console/badges";
import { CATEGORY_LABEL, formatRelative, REGION_LABEL } from "@/lib/format";
import type { CardView } from "@/lib/types";

export function NewsCard({ view, now }: { view: CardView; now?: Date }) {
  const { item, card } = view;
  const title = card.title_ko ?? item.title;
  const showOriginal = card.title_ko !== null && card.title_ko.trim() !== item.title.trim();
  return (
    <article className="group flex h-full flex-col rounded-xl border bg-card p-4 transition-colors hover:border-primary/40">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <TrackBadge track={item.track} />
        <span className="truncate">{CATEGORY_LABEL[item.category] ?? item.category}</span>
        <time className="ml-auto shrink-0" dateTime={item.published_at ?? item.first_seen_at}>
          {formatRelative(item.published_at ?? item.first_seen_at, now)}
        </time>
      </div>
      <h3 className="mt-3 line-clamp-3 text-[15px] leading-snug font-semibold text-balance">
        <Link href={`/console/items/${item.id}`} className="hover:underline">
          {title}
        </Link>
      </h3>
      {showOriginal ? <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{item.title}</p> : null}
      {card.summary_ko.length > 0 ? (
        <ul className="mt-3 space-y-1.5 text-sm leading-relaxed text-muted-foreground">
          {card.summary_ko.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-primary/70" aria-hidden />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {card.keywords.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {card.keywords.map((keyword) => (
            <Link
              key={keyword}
              href={`/console/cards?q=${encodeURIComponent(keyword)}`}
              className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
            >
              #{keyword}
            </Link>
          ))}
        </div>
      ) : null}
      <div className="mt-auto pt-4">
        <div className="flex items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
          <span className="truncate font-medium text-foreground/80">{item.source_name}</span>
          <span className="shrink-0">· {REGION_LABEL[item.region]}</span>
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex shrink-0 items-center gap-1 hover:text-foreground"
          >
            원문 <ExternalLink className="size-3" aria-hidden />
          </a>
        </div>
      </div>
    </article>
  );
}
