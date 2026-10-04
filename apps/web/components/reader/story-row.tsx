import Link from "next/link";

import { TrackBadge } from "@/components/console/badges";
import { BusinessTag, FieldTag, ImpactBadge } from "@/components/reader/labels";
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
    <article className="grid gap-1.5 border-b py-4 [content-visibility:auto] [contain-intrinsic-size:auto_140px]">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <FieldTag field={item.field} />
        {item.businesses.map((business) => (
          <BusinessTag key={business} business={business} />
        ))}
        <TrackBadge track={item.track} />
        <span className="truncate">{item.source_name}</span>
        <time className="ml-auto shrink-0" dateTime={item.first_seen_at}>
          {formatRelative(item.first_seen_at, now)}
        </time>
      </div>
      <h3 className="text-base leading-snug font-semibold">
        <Link href={`/items/${item.id}`} scroll={false} className="hover:text-primary hover:underline">
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
    </article>
  );
}
