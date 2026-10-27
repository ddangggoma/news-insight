import { AppLink as Link } from "@/components/app-link";
import { CompanyChips, FieldTag, SignalTag } from "@/components/reader/labels";
import { formatDay } from "@/lib/format";
import { articleDate } from "@/lib/patent-types";
import type { ReaderItem } from "@/lib/reader-types";

/** A recent patent signal: where and when it appeared, what it is, and who it concerns. */
export function PatentCard({ item }: { item: ReaderItem }) {
  const day = articleDate(item);
  return (
    <article className="flex min-w-0 flex-col gap-2 rounded-2xl border bg-card p-4 shadow-xs [content-visibility:auto] [contain-intrinsic-size:auto_180px]">
      <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
        <span className="truncate font-medium text-ink-2">{item.source_name}</span>
        <time className="ml-auto shrink-0 tabular-nums" dateTime={day}>
          {formatDay(day)}
        </time>
      </div>
      <h3 className="line-clamp-2 text-[15px] leading-snug font-semibold">
        <Link href={`/items/${item.id}`} scroll={false} className="hover:text-primary hover:underline">
          {item.title_ko ?? item.title}
        </Link>
      </h3>
      {item.summary_ko.length ? <p className="line-clamp-2 text-sm leading-relaxed text-ink-2">{item.summary_ko.join(" ")}</p> : null}
      <div className="flex-1" />
      <div className="flex flex-wrap items-center gap-1.5">
        <FieldTag field={item.field} />
        <SignalTag signal={item.signal_type} />
      </div>
      <CompanyChips companies={item.companies} max={3} />
    </article>
  );
}
