import { Badge } from "@/components/ui/badge";
import { type SpotlightEntry, metricChips, visibleSignals } from "@/lib/spotlight-types";
import { cn } from "@/lib/utils";

/** Change against the previous day's list: NEW, ▲n or ▼n (nothing when unchanged). */
function ChangeBadge({ entry }: { entry: Pick<SpotlightEntry, "change" | "change_by"> }) {
  if (entry.change === "new")
    return (
      <span role="img" aria-label="새로 진입" className="text-[11px] font-bold text-primary">
        NEW
      </span>
    );
  if (entry.change === "up")
    return (
      <span role="img" aria-label={`${entry.change_by}계단 상승`} className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
        {`▲${entry.change_by}`}
      </span>
    );
  if (entry.change === "down")
    return (
      <span role="img" aria-label={`${entry.change_by}계단 하락`} className="text-[11px] font-semibold text-rose-600 dark:text-rose-400">
        {`▼${entry.change_by}`}
      </span>
    );
  return null;
}

/** Opus's insight tags (neutral) and the server's signal tags (muted), each once. */
export function EntryTags({ entry }: { entry: Pick<SpotlightEntry, "tags" | "signals" | "metrics"> }) {
  const tags = entry.tags ?? [];
  const signals = visibleSignals(entry).filter((signal) => !tags.includes(signal));
  if (tags.length === 0 && signals.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1" aria-label="주목 이유">
      {tags.map((tag) => (
        <li key={`t-${tag}`} className="rounded-sm bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground">
          {tag}
        </li>
      ))}
      {signals.map((signal) => (
        <li key={`s-${signal}`} className="rounded-sm border border-dashed px-1.5 py-0.5 text-xs text-muted-foreground">
          {signal}
        </li>
      ))}
    </ul>
  );
}

/** One line of a section's list: rank, change, title, field, Opus's summary and reason, the tags and the raw metrics. */
export function EntryRow({ entry }: { entry: SpotlightEntry }) {
  const signals = new Set(visibleSignals(entry));
  const chips = metricChips(entry.metrics).filter((chip) => !signals.has(chip));
  const others = entry.item_ids.length - 1;
  return (
    <div className="flex gap-3 py-3">
      <div className="flex w-10 shrink-0 flex-col items-center gap-0.5">
        <span className="text-xl font-semibold tabular-nums">{entry.rank}</span>
        <ChangeBadge entry={entry} />
        {entry.stat_rank !== entry.rank && <span className="text-[10px] whitespace-nowrap text-muted-foreground">{`통계 ${entry.stat_rank}위`}</span>}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {entry.url ? (
            <a href={entry.url} target="_blank" rel="noopener noreferrer" className="font-medium leading-snug hover:text-primary hover:underline">
              {entry.title_ko}
            </a>
          ) : (
            <span className="font-medium leading-snug">{entry.title_ko}</span>
          )}
          {entry.product_name && <Badge variant="outline">{entry.product_name}</Badge>}
          {entry.field_label && (
            <Badge variant="ghost" className="border-border bg-muted/60 text-muted-foreground">
              <span className="sr-only">분야 </span>
              {entry.field_label}
            </Badge>
          )}
          {entry.fallback && <Badge variant="secondary">Opus 미작성</Badge>}
        </div>
        <EntryTags entry={entry} />
        {entry.summary && <p className="text-sm text-muted-foreground">{entry.summary}</p>}
        {entry.why_hot && <p className="text-sm">{entry.why_hot}</p>}
        {entry.rank_note && <p className="text-xs text-muted-foreground">{entry.rank_note}</p>}
        {(chips.length > 0 || others > 0) && (
          <ul className="flex flex-wrap gap-1.5 pt-0.5" aria-label="화제 지표">
            {chips.map((chip) => (
              <li key={chip} className={cn("rounded-full border px-2 py-0.5 text-xs text-muted-foreground")}>
                {chip}
              </li>
            ))}
            {others > 0 && <li className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">{`같은 건 ${others}건 더`}</li>}
          </ul>
        )}
      </div>
    </div>
  );
}
