import { ChevronRight } from "lucide-react";

import { AppLink as Link } from "@/components/app-link";
import { EMPTY_FILTERED, EMPTY_SECTION } from "@/components/reader/spotlight/section-list";
import {
  GROUP_KEYS,
  GROUP_LABEL,
  type GroupKey,
  SECTION_KEYS,
  SECTION_LABEL,
  type SpotlightEntry,
  type SpotlightView,
  splitGroups,
  spotlightHref,
} from "@/lib/spotlight-types";

/** Per section block: the top three of 최근 24시간 and the top two of 지속 주목. */
const TOP: Record<GroupKey, number> = { now: 3, sustained: 2 };

function OverviewRow({ entry }: { entry: SpotlightEntry }) {
  const tags = entry.tags ?? [];
  return (
    <li className="flex gap-2.5">
      <span className="w-5 shrink-0 text-right font-semibold tabular-nums">{entry.rank}</span>
      <div className="min-w-0 space-y-0.5">
        {entry.url ? (
          <a href={entry.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium leading-snug hover:text-primary hover:underline">
            {entry.title_ko}
          </a>
        ) : (
          <span className="text-sm font-medium leading-snug">{entry.title_ko}</span>
        )}
        {tags.length > 0 && (
          <ul className="flex flex-wrap gap-1" aria-label="주목 이유">
            {tags.map((tag) => (
              <li key={tag} className="rounded-sm bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground">
                {tag}
              </li>
            ))}
          </ul>
        )}
        {entry.why_hot && <p className="line-clamp-2 text-xs text-muted-foreground">{entry.why_hot}</p>}
      </div>
    </li>
  );
}

/**
 * The 전체 tab: Opus's one-line headline and, per section, the top of each group. `date` is the
 * day the reader asked for (none for a plain /spotlight, which keeps rolling forward); `view`
 * may already be narrowed by the filters (`filtered`), and `groups` limits the groups shown.
 */
export function Overview({
  view,
  date,
  groups = GROUP_KEYS,
  filtered = false,
}: {
  view: SpotlightView;
  date: string | null;
  groups?: readonly GroupKey[];
  filtered?: boolean;
}) {
  return (
    <div className="space-y-5">
      {view.headline ? (
        <p className="rounded-lg border bg-muted/40 px-4 py-3 text-base font-medium leading-relaxed">{view.headline}</p>
      ) : (
        view.date === null && <p className="text-sm text-muted-foreground">아직 발행된 목록이 없습니다.</p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {SECTION_KEYS.map((key) => {
          const split = splitGroups(view.sections[key] ?? []);
          const shown = groups.filter((group) => split[group].length > 0);
          return (
            <section key={key} className="rounded-lg border p-4">
              <h2 className="mb-2 text-sm font-semibold">
                <Link href={spotlightHref(key, date)} className="inline-flex items-center gap-0.5 hover:text-primary">
                  {SECTION_LABEL[key]}
                  <ChevronRight className="size-4" aria-hidden />
                </Link>
              </h2>
              {shown.length === 0 ? (
                <p className="py-3 text-sm text-muted-foreground">{filtered ? EMPTY_FILTERED : EMPTY_SECTION}</p>
              ) : (
                <div className="space-y-3">
                  {shown.map((group) => (
                    <div key={group} className="space-y-1.5">
                      <h3 className="text-xs font-medium text-muted-foreground">{GROUP_LABEL[group]}</h3>
                      <ol className="space-y-2">
                        {split[group].slice(0, TOP[group]).map((entry) => (
                          <OverviewRow key={`${group}-${entry.key}`} entry={entry} />
                        ))}
                      </ol>
                    </div>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
