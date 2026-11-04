"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { Legend, useHiddenSeries } from "@/components/chart-frame";
import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { type Flag, type Span, type WindowCount, seriesColor, shortDay, spanLabel } from "@/lib/domain-types";

// The 연구·특허 charts (plan 19): lines per window, theme bars against the previous window and
// a stacked field mix. Each sits inside a ChartPanel (chart-frame.tsx): zoom, full screen, and a
// legend whose entries hide series (library charts read useHiddenSeries()).

const config = {} satisfies ChartConfig;

export interface LineSeries {
  key: string;
  label: string;
  counts: number[];
  flag?: Flag | null;
}

type Row = Record<string, number | string>;

function TipBox({ title, lines }: { title: string; lines: { key: string; label: string; color: string; value: string }[] }) {
  return (
    <div className="grid min-w-40 gap-1 rounded-lg border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur">
      <div className="text-muted-foreground">{title}</div>
      {lines.map((line) => (
        <div key={line.key} className="flex items-center gap-1.5 text-ink-2">
          <span aria-hidden className="size-2 shrink-0 rounded-[2px]" style={{ background: line.color }} />
          <span className="truncate">{line.label}</span>
          <span className="ml-auto pl-2 font-semibold tabular-nums text-foreground">{line.value}</span>
        </div>
      ))}
    </div>
  );
}

const flagMark = (flag: Flag | null | undefined) => (flag === "rise" ? " ▲" : flag === "fall" ? " ▼" : "");

/**
 * One line per series over the trend windows, oldest first. A series flagged as rising or
 * falling (z ≥ 2 against the windows before) gets a ringed dot on its last window and ▲/▼ in the
 * legend. Colour follows the series' place in the list (slots 1-8, 기타 grey).
 */
export function SeriesChart({ buckets, series, unit = "건", height = 256 }: { buckets: Span[]; series: LineSeries[]; unit?: string; height?: number }) {
  const hidden = useHiddenSeries();
  const colors = series.map((s, i) => seriesColor(i, s.key));
  const data: Row[] = buckets.map((bucket, i) => {
    const row: Row = { label: shortDay(bucket.end), span: spanLabel(bucket) };
    series.forEach((s, j) => (row[`s${j}`] = s.counts[i] ?? 0));
    return row;
  });
  const last = buckets.length - 1;
  return (
    <div className="space-y-2">
      <ChartContainer config={config} className="aspect-auto w-full" style={{ height }}>
        <LineChart data={data} margin={{ left: 0, right: 12, top: 10, bottom: 0 }} accessibilityLayer>
          <CartesianGrid vertical={false} strokeOpacity={0.5} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={8} interval="preserveStartEnd" />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={32} />
          <ChartTooltip
            cursor={{ strokeOpacity: 0.3 }}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as Row | undefined;
              if (!active || !row) return null;
              const lines = series
                .map((s, j) => ({ key: s.key, label: `${s.label}${flagMark(s.flag)}`, color: colors[j], value: `${row[`s${j}`]}${unit}`, n: Number(row[`s${j}`]) }))
                .filter((line) => !hidden.has(line.key))
                .sort((a, b) => b.n - a.n);
              return <TipBox title={String(row.span)} lines={lines} />;
            }}
          />
          {series.map((s, j) =>
            hidden.has(s.key) ? null : (
              <Line
                key={s.key}
                dataKey={`s${j}`}
                name={s.label}
                type="linear"
                stroke={colors[j]}
                strokeWidth={s.key === "rest" ? 1.5 : 2}
                strokeDasharray={s.key === "rest" ? "4 3" : undefined}
                isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; index?: number }) =>
                  s.flag && props.index === last && props.cx !== undefined && props.cy !== undefined ? (
                    <circle key={`flag-${s.key}`} cx={props.cx} cy={props.cy} r={5} fill="var(--card)" stroke={colors[j]} strokeWidth={2.5}>
                      <title>{`${s.label} ${s.flag === "rise" ? "급증" : "급감"}`}</title>
                    </circle>
                  ) : (
                    <g key={`dot-${s.key}-${props.index}`} />
                  )
                }
              />
            ),
          )}
        </LineChart>
      </ChartContainer>
      {series.length > 1 ? <Legend items={series.map((s, j) => ({ key: s.key, label: `${s.label}${flagMark(s.flag)}`, swatch: colors[j], shape: "dot" as const }))} /> : null}
    </div>
  );
}

/** Theme counts of the window against the previous one, busiest first (top 10). */
export function ThemeBars({ themes }: { themes: WindowCount[] }) {
  const hidden = useHiddenSeries();
  const rows = themes.filter((t) => t.count || t.previous).slice(0, 10);
  const bars = [
    { key: "previous", label: "직전 기간", color: "var(--cat-other)" },
    { key: "count", label: "이번 기간", color: "var(--cat-1)" },
  ].filter((b) => !hidden.has(b.key));
  return (
    <div className="space-y-2">
      <ChartContainer config={config} className="aspect-auto w-full" style={{ height: Math.max(120, rows.length * 34 + 16) }}>
        <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 28, top: 4, bottom: 4 }} barGap={1} barCategoryGap={6} accessibilityLayer>
          <CartesianGrid horizontal={false} strokeOpacity={0.5} />
          <XAxis type="number" allowDecimals={false} hide />
          <YAxis type="category" dataKey="label" width={128} interval={0} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} tickFormatter={(v: string) => (v.length > 12 ? `${v.slice(0, 11)}…` : v)} />
          <ChartTooltip
            cursor={{ fillOpacity: 0.08 }}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as WindowCount | undefined;
              if (!active || !row) return null;
              return (
                <TipBox
                  title={row.label}
                  lines={[
                    { key: "count", label: "이번 기간", color: "var(--cat-1)", value: `${row.count}건` },
                    { key: "previous", label: "직전 기간", color: "var(--cat-other)", value: `${row.previous}건` },
                  ]}
                />
              );
            }}
          />
          {bars.map((b) => (
            <Bar key={b.key} dataKey={b.key} name={b.label} fill={b.color} radius={[0, 3, 3, 0]} isAnimationActive={false} maxBarSize={12} />
          ))}
        </BarChart>
      </ChartContainer>
      <Legend
        items={[
          { key: "count", label: "이번 기간", swatch: "var(--cat-1)" },
          { key: "previous", label: "직전 기간", swatch: "var(--cat-other)" },
        ]}
      />
    </div>
  );
}

export interface MixRow {
  key: string;
  label: string;
  fields: WindowCount[];
}

const MIX_FIELDS = 7;

/**
 * Each watched company's field mix in the window as one stacked bar. The seven fields busiest
 * across the companies keep a colour; the rest are summed as 기타.
 */
export function FieldMixBars({ rows }: { rows: MixRow[] }) {
  const hidden = useHiddenSeries();
  const totals = new Map<string, { label: string; n: number }>();
  for (const row of rows) {
    for (const f of row.fields) {
      const seen = totals.get(f.key);
      totals.set(f.key, { label: f.label, n: (seen?.n ?? 0) + f.count });
    }
  }
  const top = [...totals.entries()].filter(([, v]) => v.n > 0).sort((a, b) => b[1].n - a[1].n);
  const keys = top.slice(0, MIX_FIELDS).map(([key, v]) => ({ key, label: v.label }));
  if (top.length > MIX_FIELDS) keys.push({ key: "rest", label: "기타" });
  const colors = new Map(keys.map((k, i) => [k.key, seriesColor(i, k.key)]));
  const kept = new Set(keys.map((k) => k.key));
  const data: Row[] = rows.map((row) => {
    const out: Row = { label: row.label, total: 0 };
    for (const k of keys) out[k.key] = 0;
    for (const f of row.fields) {
      const key = kept.has(f.key) && f.key !== "rest" ? f.key : "rest";
      out[key] = Number(out[key] ?? 0) + f.count;
      out.total = Number(out.total) + f.count;
    }
    return out;
  });
  const shown = keys.filter((k) => !hidden.has(k.key));
  return (
    <div className="space-y-2">
      <ChartContainer config={config} className="aspect-auto w-full" style={{ height: Math.max(120, rows.length * 30 + 16) }}>
        <BarChart data={data} layout="vertical" margin={{ left: 0, right: 28, top: 4, bottom: 4 }} barCategoryGap={5} accessibilityLayer>
          <CartesianGrid horizontal={false} strokeOpacity={0.5} />
          <XAxis type="number" allowDecimals={false} hide />
          <YAxis type="category" dataKey="label" width={112} interval={0} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} tickFormatter={(v: string) => (v.length > 10 ? `${v.slice(0, 9)}…` : v)} />
          <ChartTooltip
            cursor={{ fillOpacity: 0.08 }}
            content={({ active, payload }) => {
              const row = payload?.[0]?.payload as Row | undefined;
              if (!active || !row) return null;
              const lines = shown.filter((k) => Number(row[k.key]) > 0).map((k) => ({ key: k.key, label: k.label, color: colors.get(k.key)!, value: `${row[k.key]}건` }));
              return <TipBox title={`${row.label} · ${row.total}건`} lines={lines} />;
            }}
          />
          {shown.map((k, index) => (
            <Bar
              key={k.key}
              dataKey={k.key}
              name={k.label}
              stackId="mix"
              fill={colors.get(k.key)}
              stroke="var(--card)"
              strokeWidth={1}
              isAnimationActive={false}
              maxBarSize={18}
              radius={index === shown.length - 1 ? [0, 3, 3, 0] : 0}
            />
          ))}
        </BarChart>
      </ChartContainer>
      <Legend items={keys.map((k) => ({ key: k.key, label: k.label, swatch: colors.get(k.key)! }))} />
    </div>
  );
}
