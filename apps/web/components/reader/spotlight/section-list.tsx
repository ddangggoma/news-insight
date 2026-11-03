import { EntryRow } from "@/components/reader/spotlight/entry-row";
import type { SpotlightEntry } from "@/lib/spotlight-types";

export const EMPTY_SECTION = "오늘은 기준을 넘는 화제가 없습니다";

/** One section's Top 10 (fewer when the rest fell below the bar). */
export function SectionList({ entries }: { entries: SpotlightEntry[] }) {
  if (entries.length === 0) return <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{EMPTY_SECTION}</p>;
  return (
    <ol className="divide-y rounded-lg border px-4">
      {entries.map((entry) => (
        <li key={entry.key}>
          <EntryRow entry={entry} />
        </li>
      ))}
    </ol>
  );
}
