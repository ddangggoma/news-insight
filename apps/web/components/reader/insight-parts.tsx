import type { ReactNode } from "react";

import { AppLink as Link } from "@/components/app-link";
import { Sparkline } from "@/components/reader/sparkline";
import { cn } from "@/lib/utils";

export interface Stat {
  label: string;
  value: string;
  unit?: string;
  note?: ReactNode;
}

/** Headline figures in one strip: cells share the border, two per row on a phone. */
export function StatStrip({ stats, className }: { stats: Stat[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-2 gap-px overflow-hidden rounded-2xl border bg-border md:grid-cols-4", className)}>
      {stats.map((stat) => (
        <div key={stat.label} className="flex min-w-0 flex-col gap-1 bg-card px-4 py-3.5">
          <dt className="text-xs text-muted-foreground">{stat.label}</dt>
          <dd className="min-w-0">
            <span className="text-2xl font-bold tracking-tight tabular-nums">{stat.value}</span>
            {stat.unit ? <span className="ml-0.5 text-sm text-ink-2">{stat.unit}</span> : null}
            {stat.note ? <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{stat.note}</div> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export interface RankRow {
  key: string;
  label: string;
  href?: string;
  value: number;
  /** Shown at the right; defaults to the value. */
  display?: string;
  sub?: ReactNode;
  /** Bar fill; the primary colour when not set. */
  color?: string;
  /** Counts per period, oldest first, for a sparkline. */
  trend?: number[];
  change?: ReactNode;
}

/** A ranked list where each row's bar is its share of the largest value. */
export function RankBars({ rows, empty, className }: { rows: RankRow[]; empty: string; className?: string }) {
  if (!rows.length) return <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>;
  const peak = Math.max(...rows.map((row) => row.value), 1);
  return (
    <ol className={cn("space-y-2.5", className)}>
      {rows.map((row) => {
        const label = row.href ? (
          <Link href={row.href} className="truncate font-medium hover:text-primary hover:underline">
            {row.label}
          </Link>
        ) : (
          <span className="truncate font-medium">{row.label}</span>
        );
        return (
          <li key={row.key} className="min-w-0">
            <div className="flex items-baseline gap-2 text-sm">
              {label}
              {row.change ? <span className="shrink-0 text-xs">{row.change}</span> : null}
              <span className="ml-auto shrink-0 font-semibold tabular-nums">{row.display ?? row.value}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full" style={{ width: `${Math.max(2, (row.value / peak) * 100)}%`, background: row.color ?? "var(--primary)" }} />
              </div>
              {row.trend && row.trend.length > 1 ? <Sparkline values={row.trend} width={56} height={16} label={`${row.label} 추이`} /> : null}
            </div>
            {row.sub ? <div className="mt-0.5 truncate text-xs text-muted-foreground">{row.sub}</div> : null}
          </li>
        );
      })}
    </ol>
  );
}

/** "+3", "−2" in the impact colours; "새로" for a first appearance. */
export function CountChange({ current, previous }: { current: number; previous: number }) {
  if (previous === 0) {
    return current > 0 ? <span className="font-semibold text-primary">새로</span> : null;
  }
  const diff = current - previous;
  if (diff === 0) return <span className="text-muted-foreground tabular-nums">±0</span>;
  return (
    <span className={cn("font-semibold tabular-nums", diff > 0 ? "text-impact-opportunity" : "text-impact-risk")}>
      {diff > 0 ? "▲" : "▼"}
      {Math.abs(diff)}
    </span>
  );
}
