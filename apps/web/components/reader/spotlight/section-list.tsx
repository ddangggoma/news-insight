import { EntryRow } from "@/components/reader/spotlight/entry-row";
import { GROUP_KEYS, GROUP_LABEL, type GroupKey, type SpotlightEntry, splitGroups } from "@/lib/spotlight-types";

export const EMPTY_SECTION = "오늘은 기준을 넘는 화제가 없습니다";
export const EMPTY_FILTERED = "조건에 맞는 항목이 없습니다";
const EMPTY_GROUP: Record<GroupKey, string> = { now: "최근 24시간에 기준을 넘은 화제가 없습니다", sustained: "여러 날 이어진 화제가 없습니다" };

/**
 * One section's lists: 최근 24시간 (up to 10) then 지속 주목 (up to 5), each under a small
 * heading with its count. `groups` limits which are shown (the group filter); `filtered` says a
 * filter emptied the list rather than the day.
 */
export function SectionList({ entries, groups = GROUP_KEYS, filtered = false }: { entries: SpotlightEntry[]; groups?: readonly GroupKey[]; filtered?: boolean }) {
  if (entries.length === 0)
    return <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{filtered ? EMPTY_FILTERED : EMPTY_SECTION}</p>;
  const split = splitGroups(entries);
  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <section key={group} aria-labelledby={`spotlight-group-${group}`} className="space-y-2">
          <h2 id={`spotlight-group-${group}`} className="flex items-baseline gap-1.5 text-sm font-semibold">
            {GROUP_LABEL[group]}
            <span className="text-xs font-normal text-muted-foreground tabular-nums">{`${split[group].length}건`}</span>
          </h2>
          {split[group].length === 0 ? (
            <p className="rounded-lg border border-dashed px-4 py-4 text-center text-sm text-muted-foreground">{filtered ? EMPTY_FILTERED : EMPTY_GROUP[group]}</p>
          ) : (
            <ol className="divide-y rounded-lg border px-4">
              {split[group].map((entry) => (
                <li key={`${group}-${entry.key}`}>
                  <EntryRow entry={entry} />
                </li>
              ))}
            </ol>
          )}
        </section>
      ))}
    </div>
  );
}
