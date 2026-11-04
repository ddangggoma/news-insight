"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { CartesianGrid, ErrorBar, LabelList, Scatter, ScatterChart, XAxis, YAxis } from "recharts";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { paretoFrontier } from "@/components/reader/benchmarks/frontier";
import { ChangeMark, ProviderDot, ProviderLegend, Segmented, TipBox } from "@/components/reader/benchmarks/parts";
import { PROVIDER_CHART_CONFIG, providerPaint } from "@/components/reader/benchmarks/provider-colors";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { formatCompact, formatUsd } from "@/lib/benchmark-types";
import type { DeepSweView, DsPoint as Point } from "@/lib/benchmark-view";

type Axis = "cost" | "tokens" | "steps";
type Effort = "best" | "all";
const TABLE_ROWS = 20;

const AXES: Record<Axis, { label: string; title: string; tick: (v: number) => string }> = {
  cost: { label: "비용", title: "작업당 평균 비용", tick: (v) => `$${v}` },
  tokens: { label: "출력 토큰", title: "작업당 평균 출력 토큰", tick: (v) => formatCompact(v) },
  steps: { label: "에이전트 단계", title: "작업당 평균 에이전트 단계", tick: (v) => `${v}` },
};

const xOf = (point: Point, axis: Axis) => (axis === "cost" ? point.cost : axis === "tokens" ? point.tokens : point.steps);
const name = (point: Point) => (point.effort ? `${point.model} [${point.effort}]` : point.model);
const half = (point: Point) => (point.low !== null && point.high !== null ? (point.high - point.low) / 2 : null);

const col = createColumnHelper<Point>();
const columns = [
  col.accessor("model", {
    header: "모델",
    meta: { label: "모델" },
    enableHiding: false,
    cell: ({ row: { original: p } }) => (
      <span className="flex items-center gap-1.5">
        <ProviderDot provider={p.provider} />
        <span className="font-medium">{p.model}</span>
        {p.effort && <span className="rounded border px-1 text-[10px] text-muted-foreground">{p.effort}</span>}
        <ChangeMark change={p.change} by={p.changeBy} />
      </span>
    ),
  }),
  col.accessor("score", {
    header: "pass@1",
    meta: { label: "pass@1", numeric: true },
    cell: ({ row: { original: p } }) => (
      <span className="inline-flex items-baseline gap-1">
        <span className="font-semibold">{p.score.toFixed(1)}</span>
        {half(p) !== null && <span className="text-[11px] text-muted-foreground">{`±${half(p)!.toFixed(1)}`}</span>}
      </span>
    ),
  }),
  col.accessor((p) => p.cost ?? undefined, { id: "cost", header: "평균 비용", meta: { label: "평균 비용", numeric: true }, cell: ({ row }) => formatUsd(row.original.cost) }),
  col.accessor((p) => p.tokens ?? undefined, { id: "tokens", header: "출력 토큰", meta: { label: "출력 토큰", numeric: true }, cell: ({ row }) => formatCompact(row.original.tokens) }),
  col.accessor((p) => p.steps ?? undefined, {
    id: "steps",
    header: "단계",
    meta: { label: "단계", numeric: true },
    cell: ({ row }) => (row.original.steps === null ? "—" : row.original.steps.toFixed(0)),
  }),
];

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  const point = payload?.[0]?.payload;
  if (!active || !point?.model) return null;
  const ci = half(point);
  return (
    <TipBox
      title={name(point)}
      provider={point.provider}
      lines={[
        ["pass@1", `${point.score.toFixed(1)}%${ci !== null ? ` ±${ci.toFixed(1)}` : ""}`],
        [AXES.cost.label, formatUsd(point.cost)],
        [AXES.tokens.label, formatCompact(point.tokens)],
        [AXES.steps.label, point.steps === null ? "—" : point.steps.toFixed(0)],
        ...(point.harness ? [["하네스", point.harness] as [string, string]] : []),
      ]}
    />
  );
}

/**
 * DeepSWE's own chart: pass@1 (with its 95% interval) against cost, output tokens or agent
 * steps, the x axis running from expensive on the left to cheap on the right so the
 * efficient corner is top right; the dashed efficiency frontier joins the points no cheaper
 * point beats. Below it, the site's table.
 */
export function DeepSweChart({ view }: { view: DeepSweView }) {
  // the newest version first, as the site opens on it
  const [board, setBoard] = useState(view.boards[0] ?? "");
  const [axis, setAxis] = useState<Axis>("cost");
  const [effort, setEffort] = useState<Effort>("best");

  const points = useMemo(() => view.points.filter((p) => p.board === board && (effort === "all" || p.best)), [view.points, board, effort]);

  const plotted = points
    .map((p) => ({ ...p, x: xOf(p, axis), err: p.low !== null && p.high !== null ? [p.score - p.low, p.high - p.score] : [0, 0] }))
    .filter((p): p is typeof p & { x: number } => p.x !== null);
  const frontierIds = paretoFrontier(plotted.map((p) => ({ id: p.id, x: p.x, y: p.score })));
  const frontier = plotted.filter((p) => frontierIds.includes(p.id)).sort((a, b) => a.x - b.x);
  // direct labels only where they help: the frontier and the three best scores
  const top = new Set([...plotted].sort((a, b) => b.score - a.score).slice(0, 3).map((p) => p.id));
  const data = plotted.map((p) => ({ ...p, tag: frontierIds.includes(p.id) || top.has(p.id) ? name(p) : "" }));
  const yMax = Math.min(100, Math.ceil(Math.max(10, ...plotted.map((p) => p.high ?? p.score)) / 10) * 10);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {view.boards.length > 1 && (
          <Segmented label="버전" options={view.boards.map((b) => ({ key: b, label: b }))} value={board} onChange={setBoard} />
        )}
        <Segmented
          label="추론 강도"
          options={[
            { key: "best", label: "최고값만" },
            { key: "all", label: "모든 추론 강도" },
          ]}
          value={effort}
          onChange={setEffort}
        />
        <Segmented label="가로축" options={(Object.keys(AXES) as Axis[]).map((key) => ({ key, label: AXES[key].label }))} value={axis} onChange={setAxis} />
      </div>

      <figure className="space-y-1">
        <figcaption className="text-xs font-medium">DeepSWE 점수 (pass@1, 95% 구간)</figcaption>
        <div className="relative">
          <span className="pointer-events-none absolute top-1 right-3 z-10 text-[11px] text-muted-foreground italic">효율 높음 ↗</span>
          <ChartContainer config={PROVIDER_CHART_CONFIG} className="aspect-auto h-72 w-full md:h-96">
            <ScatterChart margin={{ top: 16, right: 16, bottom: 4, left: 0 }} accessibilityLayer>
              <CartesianGrid strokeOpacity={0.5} />
              <XAxis
                type="number"
                dataKey="x"
                reversed
                domain={[0, "auto"]}
                tickLine={false}
                axisLine={false}
                tickFormatter={AXES[axis].tick}
                name={AXES[axis].title}
              />
              <YAxis type="number" dataKey="score" domain={[0, yMax]} tickLine={false} axisLine={false} width={40} tickFormatter={(v: number) => `${v}%`} />
              <ChartTooltip cursor={{ strokeDasharray: "3 3" }} content={<Tip />} />
              <Scatter
                data={frontier}
                line={{ stroke: "var(--muted-foreground)", strokeWidth: 1.5, strokeDasharray: "5 4" }}
                lineType="joint"
                shape={() => <g />}
                isAnimationActive={false}
                legendType="none"
              />
              <Scatter
                data={data}
                isAnimationActive={false}
                shape={(props: { cx?: number; cy?: number; payload?: Point }) => (
                  <circle cx={props.cx} cy={props.cy} r={5} strokeWidth={2} {...providerPaint(props.payload?.provider ?? "other")} />
                )}
              >
                <ErrorBar dataKey="err" direction="y" width={0} stroke="var(--muted-foreground)" strokeOpacity={0.6} strokeWidth={1.5} />
                <LabelList dataKey="tag" position="top" offset={8} className="fill-foreground text-[10px]" />
              </Scatter>
            </ScatterChart>
          </ChartContainer>
        </div>
        <p className="text-center text-xs text-muted-foreground">{`${AXES[axis].title} (오른쪽일수록 적음)`}</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <ProviderLegend providers={plotted.map((p) => p.provider)} />
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <svg width="20" height="6" aria-hidden>
              <line x1="0" y1="3" x2="20" y2="3" stroke="currentColor" strokeWidth="1.5" strokeDasharray="5 4" />
            </svg>
            효율 경계 (더 싼 모델보다 점수가 높은 점)
          </span>
        </div>
      </figure>

      <DataTable
        label="DeepSWE 순위표"
        columns={columns}
        data={points}
        getRowId={(p) => p.id}
        initialSorting={[{ id: "score", desc: true }]}
        initialLimit={TABLE_ROWS}
      />
    </div>
  );
}
