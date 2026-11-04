"use client";

import { GROUP_KEYS, GROUP_LABEL, type GroupKey, type SpotlightFilters } from "@/lib/spotlight-types";
import { cn } from "@/lib/utils";

function Toggle({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        pressed ? "border-primary bg-primary text-primary-foreground" : "bg-background text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** The list filters: technology field chips (전체 and today's fields, with counts) and the group toggle. */
export function SpotlightFilterBar({
  fields,
  total,
  filters,
  onChange,
}: {
  fields: { key: string; label: string; count: number }[];
  total: number;
  filters: SpotlightFilters;
  onChange: (next: SpotlightFilters) => void;
}) {
  const groups: (GroupKey | null)[] = [null, ...GROUP_KEYS];
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div role="group" aria-label="분야 필터" className="flex flex-wrap gap-1.5">
        <Toggle pressed={filters.field === null} onClick={() => onChange({ ...filters, field: null })}>
          전체 <span className="tabular-nums opacity-80">{total}</span>
        </Toggle>
        {fields.map((field) => (
          <Toggle key={field.key} pressed={filters.field === field.key} onClick={() => onChange({ ...filters, field: filters.field === field.key ? null : field.key })}>
            {field.label} <span className="tabular-nums opacity-80">{field.count}</span>
          </Toggle>
        ))}
      </div>
      <div role="group" aria-label="묶음 필터" className="flex shrink-0 gap-1.5">
        {groups.map((group) => (
          <Toggle key={group ?? "all"} pressed={filters.group === group} onClick={() => onChange({ ...filters, group })}>
            {group ? GROUP_LABEL[group] : "전체"}
          </Toggle>
        ))}
      </div>
    </div>
  );
}
