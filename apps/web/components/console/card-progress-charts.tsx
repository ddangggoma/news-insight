"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { engineGroup, ENGINES, STATE_LABEL } from "@/lib/card-progress";
import { formatNumber } from "@/lib/format";
import type { CardProgress, ProgressState } from "@/lib/types";

// Categorical slots 1-4 of the validated reference palette (dataviz skill), light and dark
// steps: CVD-separated in fixed order. "재사용" is not an engine, so it stays neutral gray.
const engineConfig = {
  agy: { label: "Antigravity", theme: { light: "#2a78d6", dark: "#3987e5" } },
  codex: { label: "Codex", theme: { light: "#eb6834", dark: "#d95926" } },
  claude: { label: "Claude", theme: { light: "#1baf7a", dark: "#199e70" } },
  qwen: { label: "로컬 Qwen", theme: { light: "#eda100", dark: "#c98500" } },
  reuse: { label: "재사용(복사)", theme: { light: "#9aa3b0", dark: "#6b7380" } },
  other: { label: "기타", theme: { light: "#5b6472", dark: "#a3abb8" } },
} satisfies ChartConfig;

const flowConfig = {
  cards: { label: "카드 생성", theme: { light: "#2a78d6", dark: "#3987e5" } },
  inflow: { label: "신규 수집", theme: { light: "#eb6834", dark: "#d95926" } },
} satisfies ChartConfig;

function engineRows<T extends { cards: Record<string, number> }>(rows: T[], label: (row: T) => string) {
  return rows.map((row) => {
    const values: Record<string, number | string> = { label: label(row) };
    for (const engine of ENGINES) values[engine] = 0;
    for (const [engine, count] of Object.entries(row.cards)) {
      const group = engineGroup(engine);
      values[group] = (values[group] as number) + count;
    }
    return values;
  });
}

/** Stacked bars of ready cards per engine; only the top segment gets rounded ends. */
function EngineBars({ data, height }: { data: Record<string, number | string>[]; height: string }) {
  return (
    <ChartContainer config={engineConfig} className={`${height} w-full`}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeOpacity={0.5} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={12} />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => formatNumber(v)} />
        <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
        {ENGINES.map((engine, index) => (
          <Bar
            key={engine}
            dataKey={engine}
            stackId="cards"
            fill={`var(--color-${engine})`}
            stroke="var(--card)"
            strokeWidth={1.5}
            isAnimationActive={false}
            radius={index === ENGINES.length - 1 ? [4, 4, 0, 0] : 0}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

export function DailyEngineChart({ days }: { days: CardProgress["days"] }) {
  return <EngineBars data={engineRows(days, (d) => d.date.slice(5).replace("-", "."))} height="h-64" />;
}

export function HourlyEngineChart({ hours }: { hours: CardProgress["hours"] }) {
  return <EngineBars data={engineRows(hours, (h) => `${h.hour.slice(5, 7)}.${h.hour.slice(8, 10)} ${h.hour.slice(11)}시`)} height="h-56" />;
}

export function FlowChart({ days }: { days: CardProgress["days"] }) {
  const data = days.map((d) => ({
    label: d.date.slice(5).replace("-", "."),
    cards: Object.values(d.cards).reduce((sum, n) => sum + n, 0),
    inflow: d.inflow,
  }));
  return (
    <ChartContainer config={flowConfig} className="h-56 w-full">
      <LineChart data={data} margin={{ left: 0, right: 12, top: 8 }}>
        <CartesianGrid vertical={false} strokeOpacity={0.5} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={12} />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => formatNumber(v)} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
        <Line dataKey="cards" isAnimationActive={false} stroke="var(--color-cards)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "var(--card)" }} activeDot={{ r: 5 }} />
        <Line dataKey="inflow" isAnimationActive={false} stroke="var(--color-inflow)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "var(--card)" }} activeDot={{ r: 5 }} />
      </LineChart>
    </ChartContainer>
  );
}

const STATE_CLASS: Record<ProgressState, string> = {
  ready: "bg-[#2a78d6] dark:bg-[#3987e5]",
  pending: "bg-[#eb6834] dark:bg-[#d95926]",
  capped: "bg-[#eda100] dark:bg-[#c98500]",
  repeat: "bg-[#1baf7a] dark:bg-[#199e70]",
  failed: "bg-destructive",
  held: "bg-muted-foreground/60",
  archive: "bg-muted-foreground/30",
};

/** Where every collected item stands, as one 100 % bar with a labelled legend. */
export function StateBar({ totals }: { totals: CardProgress["totals"] }) {
  const states = Object.keys(STATE_LABEL) as ProgressState[];
  const total = Math.max(1, totals.items);
  return (
    <div className="space-y-3">
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full bg-muted" role="img" aria-label="수집 기사 상태 분포">
        {states.map((state) =>
          totals[state] > 0 ? (
            <div
              key={state}
              className={STATE_CLASS[state]}
              style={{ width: `${Math.max(0.4, (totals[state] / total) * 100)}%` }}
              title={`${STATE_LABEL[state]} ${formatNumber(totals[state])}`}
            />
          ) : null,
        )}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
        {states.map((state) => (
          <span key={state} className="flex items-center gap-1.5">
            <span className={`size-2.5 rounded-sm ${STATE_CLASS[state]}`} aria-hidden />
            {STATE_LABEL[state]} <span className="font-medium tabular-nums text-foreground">{formatNumber(totals[state])}</span>
            <span className="tabular-nums">({((totals[state] / total) * 100).toFixed(1)}%)</span>
          </span>
        ))}
      </div>
    </div>
  );
}
