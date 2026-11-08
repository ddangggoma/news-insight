"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, LabelList, XAxis, YAxis } from "recharts";

import { ChartFrame, useHiddenSeries } from "@/components/chart-frame";
import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, ProviderDot, ProviderLegend, TipBox, ToggleChip, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { PROVIDER_CHART_CONFIG, providerPaint } from "@/components/reader/benchmarks/provider-colors";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { boardLabel } from "@/lib/benchmark-types";
import { type EpochBoard, type EpochRow, epochScore } from "@/lib/benchmark-view";

const CHART_TOP = 20;
/** Each board's page on epoch.ai (its leaderboard tab). */
const PAGES: Record<string, string> = {
  eci: "https://epoch.ai/eci?tab=leaderboard",
  gpqa_diamond: "https://epoch.ai/benchmarks/gpqa-diamond?tab=leaderboard",
  frontiermath_tiers_1_3: "https://epoch.ai/benchmarks/frontiermath-tiers-1-3-v2?tab=leaderboard",
  frontiermath_tier_4: "https://epoch.ai/benchmarks/frontiermath-tier-4-v2?tab=leaderboard",
  hle: "https://epoch.ai/benchmarks/hle?tab=leaderboard",
  arc_agi_2: "https://epoch.ai/benchmarks/arc-agi-2?tab=leaderboard",
  swe_bench_verified: "https://epoch.ai/benchmarks/swe-bench-verified?tab=leaderboard",
  metr_time_horizons: "https://epoch.ai/benchmarks/metr-time-horizons?tab=leaderboard",
  cursorbench: "https://epoch.ai/benchmarks/cursorbench?tab=leaderboard",
  gdpval: "https://epoch.ai/benchmarks/gdpval?tab=leaderboard",
};

const col = createColumnHelper<EpochRow>();

function buildColumns(unit: EpochBoard["unit"]) {
  return [
    col.accessor("rank", {
      id: "model",
      header: "순위 · 모델",
      meta: { label: "모델" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <span className="w-6 text-right font-semibold tabular-nums">{r.rank}</span>
          <ProviderDot provider={r.provider} />
          <span className="max-w-60 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          <ChangeMark change={r.change} by={r.changeBy} />
        </span>
      ),
    }),
    col.accessor("value", {
      header: unit === "index" ? "ECI" : unit === "minutes" ? "시간 지평(50%)" : "점수",
      meta: { label: "점수", numeric: true },
      cell: ({ row: { original: r } }) => (
        <span className="font-semibold">
          {epochScore(r.value, unit)}
          {unit === "index" && r.low !== null && r.high !== null && (
            <span className="ml-1 text-xs font-normal text-muted-foreground">{`[${r.low.toFixed(0)}–${r.high.toFixed(0)}]`}</span>
          )}
        </span>
      ),
    }),
    col.accessor((r) => r.org ?? undefined, { id: "org", header: "조직", meta: { label: "조직" }, cell: ({ row }) => row.original.org ?? "—" }),
    col.accessor((r) => r.source ?? undefined, {
      id: "source",
      header: "출처",
      meta: { label: "출처" },
      enableSorting: false,
      cell: ({ row }) => {
        const source = row.original.source;
        if (!source) return <span className="text-muted-foreground">Epoch AI</span>;
        if (!/^https?:\/\//.test(source)) return source;
        const host = new URL(source).hostname.replace(/^www\./, "");
        return (
          <a href={source} target="_blank" rel="noopener noreferrer" className="hover:underline">
            {host}
          </a>
        );
      },
    }),
  ];
}

function EciTip({ active, payload }: { active?: boolean; payload?: { payload: EpochRow }[] }) {
  const r = payload?.[0]?.payload;
  if (!active || !r) return null;
  return (
    <TipBox
      title={r.model}
      provider={r.provider}
      org={r.org}
      lines={[
        ["ECI", r.value.toFixed(0)],
        ["구간", r.low !== null && r.high !== null ? `${r.low.toFixed(0)}–${r.high.toFixed(0)}` : "—"],
        ["순위", `${r.rank}위`],
      ]}
    />
  );
}

/** The ECI top 20 as horizontal bars from the scale's lower end, provider-coloured, with the
 * interval as an error bar. */
function EciBars({ rows }: { rows: EpochRow[] }) {
  const hidden = useHiddenSeries();
  const top = rows.slice(0, CHART_TOP);
  const data = top
    .filter((r) => !hidden.has(r.provider))
    .map((r) => ({ ...r, err: r.low !== null && r.high !== null ? [r.value - r.low, r.high - r.value] : [0, 0] }));
  const floor = Math.floor(Math.min(...top.map((r) => r.low ?? r.value)) / 5) * 5 - 5;
  return (
    <figure className="space-y-2">
      <figcaption className="text-sm font-medium">{`ECI 상위 ${top.length}개 모델`}</figcaption>
      <ChartContainer config={PROVIDER_CHART_CONFIG} className="aspect-auto w-full" style={{ height: Math.max(160, data.length * 24 + 24) }}>
        <BarChart data={data} layout="vertical" margin={{ left: 0, right: 44, top: 4, bottom: 4 }} barCategoryGap={4} accessibilityLayer>
          <CartesianGrid horizontal={false} strokeOpacity={0.5} />
          <XAxis type="number" domain={[floor, "dataMax + 4"]} tickLine={false} axisLine={false} tick={{ fontSize: 12 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="model"
            width={150}
            interval={0}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)}
          />
          <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<EciTip />} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((r) => (
              <Cell key={r.model} fill={providerPaint(r.provider).fill} />
            ))}
            <ErrorBar dataKey="err" direction="x" width={4} strokeOpacity={0.6} stroke="currentColor" />
            <LabelList dataKey="value" position="right" offset={8} className="fill-foreground text-xs" formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(0) : "")} />
          </Bar>
        </BarChart>
      </ChartContainer>
      <ProviderLegend providers={top.map((r) => r.provider)} />
    </figure>
  );
}

/**
 * Epoch AI's Benchmarking Hub: a board picker (the ECI first, then the benchmarks), each board
 * ranked as epoch.ai's leaderboard ranks it (the best result per model version), and on the ECI
 * board its top 20 as a bar chart. Scores print as the site prints them: a share in percent with
 * one decimal, METR's time horizon as a duration, the ECI whole.
 */
export function EpochCard({ boards }: { boards: EpochBoard[] }) {
  const [key, setKey] = useState(boards[0]?.key ?? "eci");
  const board = boards.find((b) => b.key === key) ?? boards[0];
  const columns = useMemo(() => buildColumns(board?.unit ?? "percent"), [board?.unit]);
  if (!board) return null;
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Epoch 벤치마크" className="flex flex-wrap gap-1.5">
        {boards.map((b) => (
          <ToggleChip key={b.key} pressed={b.key === board.key} onClick={() => setKey(b.key)}>
            {boardLabel("epoch", b.key)}
          </ToggleChip>
        ))}
      </div>
      {board.key === "eci" && (
        <ChartFrame title="Epoch Capabilities Index 상위 20">
          <EciBars rows={board.rows} />
        </ChartFrame>
      )}
      <DataTable
        key={board.key}
        label={`Epoch AI ${boardLabel("epoch", board.key)} 순위표`}
        columns={columns}
        data={board.rows}
        getRowId={(r) => `${r.rank}|${r.model}`}
        initialSorting={[{ id: "model", desc: false }]}
        initialLimit={20}
        toolbar={
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {board.total > board.rows.length ? `${board.total}개 중 상위 ${board.rows.length}개` : `${board.rows.length}개 모델`}
            <UpdatedNote day={board.updated} note={board.unit === "percent" ? "모델 버전별 최고 점수" : undefined} />
            {PAGES[board.key] && (
              <a href={PAGES[board.key]} target="_blank" rel="noopener noreferrer" className="hover:text-foreground hover:underline">
                epoch.ai에서 보기
              </a>
            )}
          </span>
        }
      />
    </div>
  );
}
