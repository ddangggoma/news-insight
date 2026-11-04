import { AppLink as Link } from "@/components/app-link";

import { TrackBadge } from "@/components/console/badges";
import { CompanyChips, SignalTag, FieldTag, ImpactBadge } from "@/components/reader/labels";
import { formatNumber, formatRelative, REGION_LABEL } from "@/lib/format";
import type { ReaderItem } from "@/lib/reader-types";

const METRIC_LABEL: Record<string, string> = { stars: "★", points: "▲", likes: "♥", reactions: "♥", score: "▲", citations: "인용" };

function topMetric(metrics: Record<string, number>): string | null {
  const entry = Object.entries(metrics).sort((a, b) => b[1] - a[1])[0];
  return entry ? `${METRIC_LABEL[entry[0]] ?? entry[0]} ${formatNumber(entry[1])}` : null;
}

export function StoryRow({ item, now }: { item: ReaderItem; now?: Date }) {
  const metric = topMetric(item.metrics);
  return (
    // the whole row opens the article dialog (the title link stretches over it); company chips stay their own links
    <article className="group/row relative -mx-3 grid gap-1.5 border-b px-3 py-4 transition-colors [content-visibility:auto] [contain-intrinsic-size:auto_140px] hover:bg-muted/50">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <FieldTag field={item.field} />
        <SignalTag signal={item.signal_type} />
        <TrackBadge track={item.track} />
        <span className="truncate">{item.source_name}</span>
        <time className="ml-auto shrink-0" dateTime={item.occurred_at}>
          {formatRelative(item.occurred_at, now)}
        </time>
      </div>
      <h3 className="text-base leading-snug font-semibold">
        <Link href={`/items/${item.id}`} scroll={false} className="after:absolute after:inset-0 group-hover/row:text-primary">
          {item.title_ko ?? item.title}
        </Link>
      </h3>
      {item.summary_ko.length ? <p className="line-clamp-2 text-sm leading-relaxed text-ink-2">{item.summary_ko.join(" ")}</p> : null}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <ImpactBadge impact={item.impact} />
        {item.relevance !== null ? <span className="tabular-nums">관련도 {item.relevance}</span> : null}
        {item.story && item.story.item_count > 1 ? (
          <span>
            관련 보도 {item.story.item_count}건 · 매체 {item.story.source_count}곳
          </span>
        ) : null}
        {metric ? <span className="tabular-nums">{metric}</span> : null}
        <span>{REGION_LABEL[item.region]}</span>
        {item.keywords.length ? <span className="text-primary">{item.keywords.slice(0, 4).map((k) => `#${k}`).join(" ")}</span> : null}
      </div>
      <div className="relative z-10 w-fit">
        <CompanyChips companies={item.companies} />
      </div>
    </article>
  );
}
