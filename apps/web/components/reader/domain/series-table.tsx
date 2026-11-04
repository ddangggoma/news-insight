import { formatNumber } from "@/lib/format";
import { type Series, type Span, shortDay, spanLabel } from "@/lib/domain-types";
import { cn } from "@/lib/utils";

/** The 추이 table view: one row per series, one column per window, flags at the end. */
export function SeriesTable({ caption, buckets, series }: { caption: string; buckets: Span[]; series: Series[] }) {
  const last = buckets.length - 1;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b text-xs">
            <th scope="col" className="py-1.5 pr-2 text-left font-semibold">
              항목
            </th>
            {buckets.map((bucket, i) => (
              <th key={bucket.start} scope="col" title={spanLabel(bucket)} className={cn("px-1 py-1.5 text-right font-semibold tabular-nums", i === last && "text-foreground")}>
                ~{shortDay(bucket.end)}
              </th>
            ))}
            <th scope="col" className="py-1.5 pl-2 text-right font-semibold">
              이전 평균
            </th>
            <th scope="col" className="py-1.5 pl-2 text-right font-semibold">
              신호
            </th>
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.key} className="border-b last:border-0">
              <th scope="row" className="max-w-40 truncate py-1.5 pr-2 text-left font-semibold">
                {s.label}
              </th>
              {s.counts.map((count, i) => (
                <td key={buckets[i]?.start ?? i} className={cn("px-1 py-1.5 text-right tabular-nums", i === last ? "font-semibold" : "text-ink-2")}>
                  {formatNumber(count)}
                </td>
              ))}
              <td className="py-1.5 pl-2 text-right text-muted-foreground tabular-nums">{s.mean.toFixed(1)}</td>
              <td className="py-1.5 pl-2 text-right whitespace-nowrap">
                {s.flag === "rise" ? (
                  <span className="font-semibold text-impact-opportunity">▲ 급증</span>
                ) : s.flag === "fall" ? (
                  <span className="font-semibold text-impact-risk">▼ 급감</span>
                ) : (
                  <span className="text-muted-foreground">–</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
