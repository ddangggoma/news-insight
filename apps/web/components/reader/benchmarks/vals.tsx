"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Scatter, ScatterChart, XAxis, YAxis } from "recharts";

import { ChartFrame, useHiddenSeries } from "@/components/chart-frame";
import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, ProviderDot, ProviderLegend, Segmented, TipBox, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { PROVIDER_CHART_CONFIG, providerPaint } from "@/components/reader/benchmarks/provider-colors";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { type ValsRow, valsCost, valsDuration, valsTokens } from "@/lib/benchmark-view";

type Ranking = "labs" | "all";
const TABLE_ROWS = 25;

const percent = (value: number) => `${value.toFixed(2)}%`;

function Tip({ active, payload }: { active?: boolean; payload?: { payload: ValsRow }[] }) {
  const r = payload?.[0]?.payload;
  if (!active || !r?.model) return null;
  return (
    <TipBox
      title={r.model}
      provider={r.provider}
      org={r.org}
      lines={[
        ["정확도", `${percent(r.accuracy)}${r.stderr !== null ? ` ± ${r.stderr.toFixed(2)}` : ""}`],
        ["테스트당 비용", valsCost(r.costPerTest)],
        ["테스트당 시간", valsDuration(r.latency)],
        ["순위", `${r.rank}위`],
      ]}
    />
  );
}

/** vals.ai's opening chart: accuracy bars, best first, one per lab until every model is asked for. */
function RankingBars({ rows }: { rows: ValsRow[] }) {
  const floor = Math.max(0, Math.floor(Math.min(...rows.map((r) => r.accuracy)) / 10) * 10 - 10);
  return (
    <ChartContainer config={PROVIDER_CHART_CONFIG} className="aspect-auto w-full" style={{ height: Math.max(140, rows.length * 24 + 24) }}>
      <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 56, top: 4, bottom: 4 }} barCategoryGap={4} accessibilityLayer>
        <CartesianGrid horizontal={false} strokeOpacity={0.5} />
        <XAxis type="number" domain={[floor, "dataMax + 2"]} tickLine={false} axisLine={false} tick={{ fontSize: 12 }} tickFormatter={(v: number) => `${v}%`} allowDecimals={false} />
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
        <ChartTooltip cursor={{ fillOpacity: 0.08 }} content={<Tip />} />
        <Bar dataKey="accuracy" radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {rows.map((r) => (
            <Cell key={r.model} fill={providerPaint(r.provider).fill} />
          ))}
          <LabelList dataKey="accuracy" position="right" offset={8} className="fill-foreground text-xs" formatter={(v: unknown) => (typeof v === "number" ? percent(v) : "")} />
        </Bar>
      </BarChart>
    </ChartContainer>
  );
}

/** Accuracy against cost per test: up and to the left is better for the money. */
function CostScatter({ rows }: { rows: ValsRow[] }) {
  const priced = rows.filter((r) => r.costPerTest !== null && r.costPerTest > 0);
  const labelled = new Set(priced.slice(0, 5).map((r) => r.model));
  if (priced.length === 0) return null;
  return (
    <figure className="space-y-1">
      <figcaption className="text-sm font-medium">정확도 대 테스트당 비용 (로그 눈금)</figcaption>
      <ChartContainer config={PROVIDER_CHART_CONFIG} className="aspect-auto h-72 w-full">
        <ScatterChart margin={{ top: 16, right: 16, bottom: 4, left: 0 }} accessibilityLayer>
          <CartesianGrid strokeOpacity={0.5} />
          <XAxis type="number" dataKey="costPerTest" scale="log" domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fontSize: 12 }} tickFormatter={(v: number) => `$${v}`} />
          <YAxis type="number" dataKey="accuracy" domain={["auto", "auto"]} tickLine={false} axisLine={false} width={40} tick={{ fontSize: 12 }} tickFormatter={(v: number) => `${v}%`} />
          <ChartTooltip cursor={{ strokeDasharray: "3 3" }} content={<Tip />} />
          <Scatter
            data={priced.map((r) => ({ ...r, tag: labelled.has(r.model) ? r.model : "" }))}
            isAnimationActive={false}
            shape={(props: { cx?: number; cy?: number; payload?: ValsRow }) => <circle cx={props.cx} cy={props.cy} r={5} strokeWidth={2} {...providerPaint(props.payload?.provider ?? "other")} />}
          >
            <LabelList dataKey="tag" position="top" offset={8} className="fill-foreground text-xs" />
          </Scatter>
        </ScatterChart>
      </ChartContainer>
      <p className="text-xs text-muted-foreground">왼쪽 위일수록 적은 비용으로 높은 정확도</p>
    </figure>
  );
}

function Charts({ rows, ranking }: { rows: ValsRow[]; ranking: Ranking }) {
  const hidden = useHiddenSeries();
  const pool = ranking === "labs" ? rows.filter((r) => r.labBest) : rows;
  // providers switched off in the legend leave the charts, not the legend
  const shown = pool.filter((r) => !hidden.has(r.provider));
  return (
    <div className="space-y-5">
      <figure className="space-y-2">
        <figcaption className="text-sm font-medium">{ranking === "labs" ? `개발사별 최고 모델 ${pool.length}개` : `전체 모델 ${pool.length}개`}</figcaption>
        <RankingBars rows={shown} />
      </figure>
      <CostScatter rows={rows.filter((r) => !hidden.has(r.provider))} />
      <ProviderLegend providers={rows.map((r) => r.provider)} />
    </div>
  );
}

const col = createColumnHelper<ValsRow>();

function buildColumns() {
  // vals.ai's table: Rank, Model, Accuracy, Cost / Test, Tokens / Test, Duration / Test
  return [
    col.accessor("rank", {
      header: "순위",
      meta: { label: "순위", numeric: true },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center justify-end gap-1">
          <span className="font-semibold tabular-nums">{r.rank}</span>
          <ChangeMark change={r.change} by={r.changeBy} />
        </span>
      ),
    }),
    col.accessor("model", {
      header: "모델",
      meta: { label: "모델" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <ProviderDot provider={r.provider} />
          <span className="max-w-60 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {r.org && <span className="hidden text-xs text-muted-foreground sm:inline">{r.org}</span>}
          {r.open && <span className="rounded border px-1 text-xs text-muted-foreground">오픈 웨이트</span>}
        </span>
      ),
    }),
    col.accessor("accuracy", { header: "정확도", meta: { label: "정확도", numeric: true }, cell: ({ row }) => <span className="font-semibold">{percent(row.original.accuracy)}</span> }),
    col.accessor((r) => r.costPerTest ?? undefined, { id: "cost", header: "테스트당 비용", meta: { label: "테스트당 비용", numeric: true }, cell: ({ row }) => valsCost(row.original.costPerTest) }),
    col.accessor((r) => r.tokensPerTest ?? undefined, { id: "tokens", header: "테스트당 토큰", meta: { label: "테스트당 토큰", numeric: true }, cell: ({ row }) => valsTokens(row.original.tokensPerTest) }),
    col.accessor((r) => r.latency ?? undefined, { id: "duration", header: "테스트당 시간", meta: { label: "테스트당 시간", numeric: true }, cell: ({ row }) => valsDuration(row.original.latency) }),
  ];
}

/**
 * The Vals Index as vals.ai lays its page out: the accuracy ranking opening on the best model
 * of each lab (a switch shows every model), accuracy against cost per test, then the table
 * with the site's columns and number formats (71.31%, $17.94, 31.31m tokens, 43m42s).
 */
export function ValsCard({ rows, updated }: { rows: ValsRow[]; updated: string | null }) {
  const [ranking, setRanking] = useState<Ranking>("labs");
  const columns = useMemo(() => buildColumns(), []);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="순위 막대에 넣을 모델"
          options={[
            { key: "labs", label: "개발사별 최고 모델" },
            { key: "all", label: "모든 모델" },
          ]}
          value={ranking}
          onChange={(key) => setRanking(key as Ranking)}
        />
        <UpdatedNote day={updated} note="사이트 기본: 개발사별 최고 모델" />
      </div>
      <ChartFrame title="Vals Index 정확도 순위와 비용">
        <Charts rows={rows} ranking={ranking} />
      </ChartFrame>
      <DataTable
        label="Vals Index 순위표"
        columns={columns}
        data={rows}
        getRowId={(r) => `${r.rank}|${r.model}`}
        initialSorting={[{ id: "rank", desc: false }]}
        initialLimit={TABLE_ROWS}
        toolbar={<span className="text-xs text-muted-foreground">{`${rows.length}개 모델 · 금융·코딩·법률·세무 과제를 미국 GDP 비중으로 가중`}</span>}
      />
    </div>
  );
}
