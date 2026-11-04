"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { DEAL_SERIES, DEAL_SERIES_COLOR, DEAL_SERIES_LABEL, type DealBucket, type DealSeries, formatUsd } from "@/lib/deal-types";

const config = Object.fromEntries(DEAL_SERIES.map((s) => [s, { label: DEAL_SERIES_LABEL[s], color: DEAL_SERIES_COLOR[s] }])) satisfies ChartConfig;

type Row = Record<DealSeries, number> & { key: string; label: string; total: number; usd: number | null };

function Tip({ active, payload, unit }: { active?: boolean; payload?: { payload: Row }[]; unit: "week" | "month" }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  const heading = unit === "week" ? `${row.key.slice(0, 4)}.${row.label} 주` : `${row.key.slice(0, 4)}년 ${Number(row.key.slice(5, 7))}월`;
  return (
    <div className="grid min-w-36 gap-1 rounded-lg border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur">
      <div className="text-muted-foreground">{heading}</div>
      <div className="text-sm font-semibold tabular-nums">
        {row.total}건{row.usd ? <span className="ml-1.5 text-xs font-normal text-ink-2">{formatUsd(row.usd)}</span> : null}
      </div>
      {DEAL_SERIES.filter((s) => row[s] > 0).map((s) => (
        <div key={s} className="flex items-center gap-1.5 text-ink-2">
          <span aria-hidden className="size-2 rounded-[2px]" style={{ background: DEAL_SERIES_COLOR[s] }} />
          {DEAL_SERIES_LABEL[s]}
          <span className="ml-auto tabular-nums">{row[s]}</span>
        </div>
      ))}
    </div>
  );
}

/** Deals per week or month, stacked by kind; a 1.5px card-coloured stroke separates segments. */
export function DealTimeline({ buckets, unit, series }: { buckets: DealBucket[]; unit: "week" | "month"; series: DealSeries[] }) {
  const data: Row[] = buckets.map((b) => ({ key: b.key, label: b.label, total: b.total, usd: b.usd, ...b.counts }));
  return (
    <ChartContainer config={config} className="aspect-auto h-56 w-full md:h-64">
      <BarChart data={data} margin={{ left: 0, right: 4, top: 8, bottom: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} strokeOpacity={0.5} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={8} interval="preserveStartEnd" />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} />
        <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<Tip unit={unit} />} />
        {series.map((s, index) => (
          <Bar
            key={s}
            dataKey={s}
            stackId="deals"
            fill={`var(--color-${s})`}
            stroke="var(--card)"
            strokeWidth={1.5}
            isAnimationActive={false}
            maxBarSize={36}
            radius={index === series.length - 1 ? [4, 4, 0, 0] : 0}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}
