"use client";

import { useRouter } from "next/navigation";

import { FIELD_LABEL } from "@/lib/taxonomy";

/** Category drill-down: every number on the page narrows to one field. */
export function FieldPicker({ value, hrefs }: { value: string | null; hrefs: Record<string, string> }) {
  const router = useRouter();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">카테고리</span>
      <select
        value={value ?? ""}
        onChange={(event) => router.push(hrefs[event.target.value || "*"], { scroll: false })}
        className="h-8 rounded-lg border bg-background px-2 text-sm font-medium focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <option value="">전체 15개</option>
        {Object.entries(FIELD_LABEL).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}
