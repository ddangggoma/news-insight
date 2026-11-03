"use client";

import { useRouter } from "next/navigation";

import { formatBriefingDate } from "@/lib/format";
import { type SpotlightTab, spotlightHref } from "@/lib/spotlight-types";

/** Picks one of the published days; the open tab stays. */
export function DateSelect({ dates, current, tab }: { dates: string[]; current: string | null; tab: SpotlightTab }) {
  const router = useRouter();
  if (dates.length === 0) return null;
  return (
    <select
      aria-label="날짜"
      value={current ?? dates[0]}
      onChange={(event) => router.push(spotlightHref(tab, event.target.value))}
      className="h-9 rounded-md border bg-background px-2 text-sm"
    >
      {dates.map((day) => (
        <option key={day} value={day}>
          {formatBriefingDate(day)}
        </option>
      ))}
    </select>
  );
}
