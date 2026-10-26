"use client";

import { Bar, type BarShapeProps, BarChart, CartesianGrid, Rectangle, XAxis, YAxis } from "recharts";

import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { periodLabel } from "@/lib/patent-types";

// categorical slots 1-2: patent offices and news about patents
const config = {
  office: { label: "특허청 공보", color: "var(--cat-1)" },
  article: { label: "지식재산 기사", color: "var(--cat-2)" },
} satisfies ChartConfig;

type Row = { key: string; label: string; office: number; article: number; total: number; running: boolean };

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div className="grid min-w-36 gap-1 rounded-lg border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur">
      <div className="text-muted-foreground">
        {row.key}
        {row.running ? " (진행 중)" : ""}
      </div>
      <div className="text-sm font-semibold tabular-nums">{row.total}건</div>
      {(["office", "article"] as const).map((k) => (
        <div key={k} className="flex items-center gap-1.5 text-ink-2">
          <span aria-hidden className="size-2 rounded-[2px]" style={{ background: config[k].color }} />
          {config[k].label}
          <span className="ml-auto tabular-nums">{row[k]}</span>
        </div>
      ))}
    </div>
  );
}

/** The running period is drawn lighter: it is not over yet. */
function RunningBar(props: BarShapeProps) {
  const running = (props.payload as Row | undefined)?.running;
  return <Rectangle {...props} fillOpacity={running ? 0.5 : 1} />;
}

/** Patent signals per period, office publications under news about patents. */
export function PatentPeriods({ periods }: { periods: { key: string; total: number; office: number }[] }) {
  const data: Row[] = periods.map((p, i) => ({
    key: p.key,
    label: periodLabel(p.key),
    office: p.office,
    article: p.total - p.office,
    total: p.total,
    running: i === periods.length - 1,
  }));
  return (
    <ChartContainer config={config} className="aspect-auto h-56 w-full md:h-64">
      <BarChart data={data} margin={{ left: 0, right: 4, top: 8, bottom: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} strokeOpacity={0.5} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={6} interval="preserveStartEnd" />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
        <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<Tip />} />
        {(["office", "article"] as const).map((k) => (
          <Bar key={k} dataKey={k} stackId="p" fill={`var(--color-${k})`} stroke="var(--card)" strokeWidth={1.5} isAnimationActive={false} maxBarSize={40} radius={k === "article" ? [4, 4, 0, 0] : 0} shape={RunningBar} />
        ))}
      </BarChart>
    </ChartContainer>
  );
}
