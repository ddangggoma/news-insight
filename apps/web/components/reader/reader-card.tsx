"use client";

import { Bookmark, BookmarkCheck, Check, Layers } from "lucide-react";

import { TopicChips } from "@/components/reader/topic-chips";
import { useLibrary } from "@/hooks/use-library";
import { formatRelative, TRACK_LABEL } from "@/lib/format";
import type { ReaderCard as Card } from "@/lib/reader-types";
import { cn } from "@/lib/utils";

export function ReaderCard({ card, showTrack = false }: { card: Card; showTrack?: boolean }) {
  const { library, toggleBookmark, markRead } = useLibrary();
  const saved = Boolean(library.bookmarks[String(card.id)]);
  const read = Boolean(library.read[String(card.id)]);
  const title = card.title_ko || card.title;
  return (
    <article
      data-read={read || undefined}
      className="group/card flex flex-col gap-2 rounded-xl border bg-card p-4 transition-colors hover:border-primary/30"
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {showTrack ? <span className="font-medium text-foreground/70">{TRACK_LABEL[card.track]}</span> : null}
        <span className="truncate font-medium text-foreground/80">{card.source_name}</span>
        <span aria-hidden>·</span>
        <time dateTime={card.published_at ?? card.first_seen_at} className="shrink-0">
          {formatRelative(card.published_at ?? card.first_seen_at)}
        </time>
        {card.coverage && card.coverage > 1 ? (
          <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-700 dark:text-amber-300" title="같은 이슈를 다룬 매체 수">
            <Layers className="size-3" aria-hidden /> {card.coverage}개 매체
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => toggleBookmark({ id: card.id, title, url: card.url, source_name: card.source_name })}
          aria-pressed={saved}
          aria-label={saved ? "북마크 해제" : "북마크"}
          className="ml-auto rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          {saved ? <BookmarkCheck className="size-4 text-primary" /> : <Bookmark className="size-4" />}
        </button>
      </div>
      <h3 className={cn("leading-snug font-semibold", read && "text-muted-foreground")}>
        <a href={card.url} target="_blank" rel="noopener noreferrer" onClick={() => markRead(card.id)} className="hover:underline">
          {title}
        </a>
        {read ? <Check className="ml-1 inline size-3.5 text-muted-foreground" aria-label="읽음" /> : null}
      </h3>
      {card.title_ko && card.title_ko !== card.title ? (
        <p className="line-clamp-1 text-xs text-muted-foreground" lang="und">
          {card.title}
        </p>
      ) : null}
      {card.summary_ko.length > 0 ? (
        <ul className="space-y-1 text-sm leading-relaxed text-foreground/85">
          {card.summary_ko.map((line, index) => (
            <li key={index} className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <TopicChips field={card.field} themes={card.themes} businesses={card.businesses} impact={card.impact} />
    </article>
  );
}
