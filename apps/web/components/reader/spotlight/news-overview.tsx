import { Compass, Layers } from "lucide-react";

import { GROUP_LABEL, type NewsOverview, type SpotlightEntry, entryAnchor, groupOf } from "@/lib/spotlight-types";

/** The entries a theme or an area points at, in its own order; keys the day no longer lists are skipped. */
function resolve(keys: string[], byKey: Map<string, SpotlightEntry>): SpotlightEntry[] {
  return keys.flatMap((key) => byKey.get(key) ?? []);
}

/** Entry titles as links to their rows in the list below (`visible` holds the keys now shown). */
function EntryLinks({ entries, visible }: { entries: SpotlightEntry[]; visible: Set<string> }) {
  return (
    <ul className="space-y-1">
      {entries.map((entry) => {
        const label = `${GROUP_LABEL[groupOf(entry)]} ${entry.rank}위`;
        return (
          <li key={entry.key} className="flex gap-2 text-sm">
            <span className="w-9 shrink-0 text-right text-xs leading-5 font-semibold tabular-nums text-muted-foreground" title={label}>
              <span className="sr-only">{label} </span>
              {/* a 지속 주목 entry has a rank of its own: mark it so two "1"s do not read as a tie */}
              <span aria-hidden>{groupOf(entry) === "sustained" ? `지속 ${entry.rank}` : entry.rank}</span>
            </span>
            {visible.has(entry.key) ? (
              <a href={`#${entryAnchor(entry.key)}`} className="min-w-0 leading-snug hover:text-primary hover:underline">
                {entry.title_ko}
              </a>
            ) : (
              <span className="min-w-0 leading-snug">{entry.title_ko}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * 오늘의 구도 above the news list: the day's news as a few themes (what is moving and why it
 * matters), then the reader's interest areas, each with its direction and up to three entries.
 * `entries` are all the day's news entries; `visible` the ones the filters leave in the list, so
 * a title links to its row only while that row is shown. Nothing is rendered for a day published
 * before the overview.
 */
export function NewsOverviewPanel({ overview, entries, visible }: { overview: NewsOverview | null | undefined; entries: SpotlightEntry[]; visible: SpotlightEntry[] }) {
  if (!overview) return null;
  const byKey = new Map(entries.map((entry) => [entry.key, entry]));
  const shown = new Set(visible.map((entry) => entry.key));
  const themes = overview.themes.map((theme) => ({ theme, found: resolve(theme.keys, byKey) })).filter(({ found }) => found.length > 0);
  const areas = overview.areas.map((area) => ({ area, found: resolve(area.keys, byKey) })).filter(({ found }) => found.length > 0);
  if (themes.length === 0 && areas.length === 0) return null;
  return (
    <div className="space-y-5">
      {themes.length > 0 && (
        <section aria-labelledby="news-themes-title" className="space-y-2">
          <h2 id="news-themes-title" className="flex items-center gap-1.5 text-sm font-semibold">
            <Layers className="size-4 text-muted-foreground" aria-hidden />
            오늘의 구도
            <span className="text-xs font-normal text-muted-foreground">{`흐름 ${themes.length}개 (Opus)`}</span>
          </h2>
          <ol className="grid gap-3 md:grid-cols-2">
            {themes.map(({ theme, found }, index) => (
              <li key={theme.title} className="space-y-2 rounded-lg border bg-muted/30 p-4">
                <h3 className="flex items-baseline gap-2 font-semibold leading-snug">
                  <span className="text-xs tabular-nums text-muted-foreground" aria-hidden>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {theme.title}
                </h3>
                <p className="text-sm leading-relaxed">{theme.summary}</p>
                <EntryLinks entries={found} visible={shown} />
              </li>
            ))}
          </ol>
        </section>
      )}
      {areas.length > 0 && (
        <section aria-labelledby="news-areas-title" className="space-y-2">
          <h2 id="news-areas-title" className="flex items-center gap-1.5 text-sm font-semibold">
            <Compass className="size-4 text-muted-foreground" aria-hidden />
            관심 분야별 정리
            <span className="text-xs font-normal text-muted-foreground">{`${areas.length}개 분야`}</span>
          </h2>
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {areas.map(({ area, found }) => (
              <li key={area.area} className="space-y-2 rounded-lg border p-4">
                <h3 className="text-sm font-semibold text-primary">{area.label}</h3>
                <p className="text-sm leading-relaxed">{area.insight}</p>
                <EntryLinks entries={found} visible={shown} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
