"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { PERIODS, type Period, type ReaderFilters, SORTS, type Sort, setHref } from "@/lib/reader-filters";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export function FeedToolbar({ filters, total, itemsTotal }: { filters: ReaderFilters; total: number; itemsTotal: number }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3" aria-busy={pending}>
      <p className="text-sm text-muted-foreground">
        이슈 <b className="text-foreground tabular-nums">{formatNumber(total)}</b>건 · 보도{" "}
        <b className="text-foreground tabular-nums">{formatNumber(itemsTotal)}</b>건
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="기간" className="inline-flex rounded-lg bg-muted p-0.5">
          {(Object.keys(PERIODS) as Period[]).map((period) => (
            <Link
              key={period}
              href={setHref(filters, "period", period)}
              scroll={false}
              aria-current={filters.period === period ? "true" : undefined}
              className={cn(
                "rounded-md px-3 py-1 text-sm text-muted-foreground",
                filters.period === period && "bg-background font-semibold text-foreground shadow-sm",
              )}
            >
              {PERIODS[period]}
            </Link>
          ))}
        </nav>
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
          정렬
          <select
            value={filters.sort}
            onChange={(event) => startTransition(() => router.push(setHref(filters, "sort", event.target.value), { scroll: false }))}
            className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
          >
            {(Object.keys(SORTS) as Sort[]).map((sort) => (
              <option key={sort} value={sort}>
                {SORTS[sort]}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
