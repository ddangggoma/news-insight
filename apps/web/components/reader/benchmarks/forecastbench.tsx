"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, ProviderDot, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { type ForecastRow, forecastCell } from "@/lib/benchmark-view";

/** forecastbench.org pages its table by 25. */
const TABLE_ROWS = 25;

const col = createColumnHelper<ForecastRow>();

function buildColumns() {
  // forecastbench.org's tournament table: Rank, Team, Org, Model, Dataset (N), Dataset 95% CI,
  // Market (N), Market 95% CI, Overall (N), Overall 95% CI, Supers > Forecaster?, Forecaster > Public?
  return [
    col.accessor((r) => r.rank ?? undefined, {
      id: "rank",
      header: "순위",
      meta: { label: "순위", numeric: true },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center justify-end gap-1">
          <span className="font-semibold tabular-nums">{r.rank ?? "—"}</span>
          <ChangeMark change={r.change} by={r.changeBy} />
        </span>
      ),
    }),
    col.accessor("model", {
      header: "모델",
      meta: { label: "모델", cellClassName: (r) => (r.reference ? "bg-amber-500/10" : undefined) },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <ProviderDot provider={r.provider} />
          <span className="max-w-64 truncate font-medium" title={r.model}>
            {r.model}
          </span>
        </span>
      ),
    }),
    col.accessor((r) => r.team ?? undefined, { id: "team", header: "팀", meta: { label: "팀" }, cell: ({ row }) => row.original.team ?? "—" }),
    col.accessor((r) => r.org ?? undefined, { id: "org", header: "개발사", meta: { label: "개발사" }, cell: ({ row }) => row.original.org ?? "—" }),
    col.accessor((r) => r.dataset ?? undefined, {
      id: "dataset",
      header: "데이터셋 (N)",
      meta: { label: "데이터셋", numeric: true },
      cell: ({ row: { original: r } }) => forecastCell(r.dataset, r.nDataset),
    }),
    col.accessor((r) => r.datasetCi ?? undefined, { id: "datasetCi", header: "데이터셋 95% CI", meta: { label: "데이터셋 95% CI" }, enableSorting: false, cell: ({ row }) => row.original.datasetCi ?? "—" }),
    col.accessor((r) => r.market ?? undefined, {
      id: "market",
      header: "시장 (N)",
      meta: { label: "시장", numeric: true },
      cell: ({ row: { original: r } }) => forecastCell(r.market, r.nMarket),
    }),
    col.accessor((r) => r.marketCi ?? undefined, { id: "marketCi", header: "시장 95% CI", meta: { label: "시장 95% CI" }, enableSorting: false, cell: ({ row }) => row.original.marketCi ?? "—" }),
    col.accessor("overall", {
      header: "종합 (N)",
      meta: { label: "종합", numeric: true },
      cell: ({ row: { original: r } }) => <span className="font-semibold">{forecastCell(r.overall, r.n)}</span>,
    }),
    col.accessor((r) => r.low ?? undefined, {
      id: "overallCi",
      header: "종합 95% CI",
      meta: { label: "종합 95% CI" },
      enableSorting: false,
      cell: ({ row: { original: r } }) => (r.low !== null && r.high !== null ? `[${r.low.toFixed(1)}, ${r.high.toFixed(1)}]` : "—"),
    }),
    col.accessor((r) => r.supersBeat ?? undefined, { id: "supers", header: "슈퍼포캐스터 > 모델?", meta: { label: "슈퍼포캐스터 > 모델?" }, cell: ({ row }) => row.original.supersBeat ?? "—" }),
    col.accessor((r) => r.beatsPublic ?? undefined, { id: "public", header: "모델 > 일반인?", meta: { label: "모델 > 일반인?" }, cell: ({ row }) => row.original.beatsPublic ?? "—" }),
  ];
}

/**
 * ForecastBench as forecastbench.org opens its leaderboards: the Tournament tab ordered by the
 * overall Brier Index, anonymous teams hidden until asked for (so the first row can be rank 3),
 * 25 rows at a time, the superforecaster and public median rows shaded.
 */
export function ForecastBenchTable({ rows, updated }: { rows: ForecastRow[]; updated: string | null }) {
  const [anonymous, setAnonymous] = useState(false);
  const columns = useMemo(() => buildColumns(), []);
  const shown = anonymous ? rows : rows.filter((r) => !r.anonymous);
  const hidden = rows.length - rows.filter((r) => !r.anonymous).length;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        사이트 기본 보기 그대로: <span className="text-foreground">Tournament 탭 · 익명 팀 숨김</span>, 종합 Brier Index 순 (100 = 완벽, 50 = 항상 50%로 답한 수준). 순위는 익명 팀을 포함해 매긴 사이트 순위입니다.
      </p>
      <DataTable
        key={anonymous ? "all" : "named"}
        label="ForecastBench 토너먼트 순위표"
        columns={columns}
        data={shown}
        getRowId={(r) => r.id}
        initialSorting={[]}
        initialLimit={TABLE_ROWS}
        enableColumnVisibility
        initialVisibility={{ team: false }}
        toolbar={
          <span className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <label className="flex cursor-pointer items-center gap-1.5 text-foreground">
              <input type="checkbox" checked={anonymous} onChange={(event) => setAnonymous(event.target.checked)} className="size-3.5 accent-primary" />
              {`익명 팀 보기 (${hidden}개 행)`}
            </label>
            {`${shown.length}개 행`}
            <UpdatedNote day={updated} />
          </span>
        }
      />
    </div>
  );
}
