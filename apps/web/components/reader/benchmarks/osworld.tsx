"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, PercentBar, ProviderDot, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { type OsRow, osPercent } from "@/lib/benchmark-view";

/** The site's formatDisplayLabel: first letter up ("batch tool" → "Batch tool"). */
const label = (value: string | null, fallback = "—") => {
  const text = value || fallback;
  return text.charAt(0).toUpperCase() + text.slice(1);
};

const col = createColumnHelper<OsRow>();

function buildColumns() {
  return [
    col.accessor("rank", {
      id: "model",
      header: "순위 · 모델",
      meta: { label: "모델" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <span className="w-6 text-right font-semibold tabular-nums">{r.rank}</span>
          <ProviderDot provider={r.provider} />
          <span className="max-w-52 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {r.org && <span className="hidden text-xs text-muted-foreground sm:inline">{r.org}</span>}
          <ChangeMark change={r.change} by={r.changeBy} />
        </span>
      ),
    }),
    col.accessor((r) => r.reasoning ?? undefined, { id: "reasoning", header: "추론", meta: { label: "추론" }, cell: ({ row }) => label(row.original.reasoning) }),
    col.accessor((r) => r.tool ?? undefined, {
      id: "tool",
      header: "도구 설정",
      meta: { label: "도구 설정" },
      // an agent row leaves the setting empty; the site then prints nothing
      cell: ({ row }) => (row.original.tool === "" ? "—" : label(row.original.tool, "standard")),
    }),
    col.accessor((r) => r.steps ?? undefined, { id: "steps", header: "스텝", meta: { label: "스텝", numeric: true }, cell: ({ row }) => row.original.steps ?? "—" }),
    col.accessor("binary", {
      header: "성공률",
      meta: { label: "성공률" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-2">
          <span className="w-14 font-semibold tabular-nums">{osPercent(r.binary)}</span>
          <PercentBar value={r.binary} label={`성공률 ${osPercent(r.binary)}`} />
        </span>
      ),
    }),
    col.accessor((r) => r.partial ?? undefined, { id: "partial", header: "부분 점수", meta: { label: "부분 점수", numeric: true }, cell: ({ row }) => osPercent(row.original.partial) }),
    col.accessor((r) => r.costPerTask ?? undefined, {
      id: "cost",
      header: "과제당 비용",
      meta: { label: "과제당 비용", numeric: true },
      cell: ({ row }) => (row.original.costPerTask === null ? "—" : `$${row.original.costPerTask.toFixed(1)}`),
    }),
    col.accessor((r) => r.release ?? undefined, { id: "release", header: "릴리스", meta: { label: "릴리스" }, cell: ({ row }) => row.original.release ?? "—" }),
  ];
}

/**
 * OSWorld 2.0 as osworld-v2.xlang.ai opens its leaderboard: the Foundation E2E GUI tab, a
 * 500-step budget, every release, the full task set, best binary accuracy (success rate) first.
 */
export function OsWorldTable({ rows, updated }: { rows: OsRow[]; updated: string | null }) {
  const columns = useMemo(() => buildColumns(), []);
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        사이트 기본 보기 그대로: <span className="text-foreground">Foundation E2E GUI · 스텝 500 · 모든 릴리스 · 전체 세트(108개 과제)</span>, 성공률(binary accuracy) 순
      </p>
      <DataTable
        label="OSWorld 2.0 순위표"
        columns={columns}
        data={rows}
        getRowId={(r) => `${r.rank}`}
        initialSorting={[{ id: "model", desc: false }]}
        initialLimit={25}
        toolbar={
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {`${rows.length}개 결과`}
            <UpdatedNote day={updated} />
          </span>
        }
      />
    </div>
  );
}
