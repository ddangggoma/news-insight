import { X } from "lucide-react";
import Link from "next/link";

import { activeChips, clearHref, type ReaderFilters, removeHref } from "@/lib/reader-filters";

export function ActiveFilters({ filters }: { filters: ReaderFilters }) {
  const chips = activeChips(filters);
  if (!chips.length) return <span className="text-sm text-muted-foreground">분야·사업부를 골라 좁혀 보세요</span>;
  return (
    <>
      {chips.map((chip) => (
        <Link
          key={`${chip.axis}-${chip.key}`}
          href={removeHref(filters, chip.axis, chip.key)}
          scroll={false}
          aria-label={`${chip.label} 필터 해제`}
          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm font-semibold text-primary hover:bg-primary/15"
        >
          {chip.label}
          <X className="size-3.5" aria-hidden />
        </Link>
      ))}
      <Link href={clearHref(filters)} scroll={false} className="text-sm text-muted-foreground underline underline-offset-2">
        모두 지우기
      </Link>
    </>
  );
}
