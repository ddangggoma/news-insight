"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, PercentBar, ProviderDot, UpdatedNote } from "@/components/reader/benchmarks/parts";
import type { SimpleRow } from "@/lib/benchmark-view";

const TABLE_ROWS = 25;

const col = createColumnHelper<SimpleRow>();

function buildColumns() {
  // simple-bench.com's MCQ table: Rank (NEW for two weeks), Model, Score (AVG@5), Organization
  return [
    col.accessor("position", {
      id: "rank",
      header: "순위",
      meta: { label: "순위" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <span className="w-10 font-semibold tabular-nums">{r.rankLabel}</span>
          {r.isNew && <span className="rounded bg-primary/10 px-1 text-xs font-bold text-primary">NEW</span>}
          <ChangeMark change={r.change} by={r.changeBy} />
        </span>
      ),
    }),
    col.accessor("model", {
      header: "모델",
      meta: { label: "모델", cellClassName: (r) => (r.human ? "italic" : undefined) },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          {!r.human && <ProviderDot provider={r.provider} />}
          <span className="max-w-64 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {r.human && <span className="rounded border px-1 text-xs text-muted-foreground not-italic">사람 기준선</span>}
        </span>
      ),
    }),
    col.accessor("score", {
      header: "점수 (5회 평균)",
      meta: { label: "점수" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-2">
          <span className="w-14 font-semibold tabular-nums">{`${r.score.toFixed(1)}%`}</span>
          <PercentBar value={r.score} label={`점수 ${r.score.toFixed(1)}%`} />
        </span>
      ),
    }),
    col.accessor((r) => r.org ?? undefined, { id: "org", header: "개발사", meta: { label: "개발사" }, cell: ({ row }) => row.original.org ?? "" }),
  ];
}

/**
 * SimpleBench as simple-bench.com opens it: the MCQ table in the site's own order, the two
 * human reference rows in place among the models, ranks written as the site writes them
 * ("1st") and a NEW tag on rows added in the last two weeks.
 */
export function SimpleBenchTable({ rows, updated }: { rows: SimpleRow[]; updated: string | null }) {
  const columns = useMemo(() => buildColumns(), []);
  const models = rows.filter((r) => !r.human).length;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        사이트 기본 보기 그대로: <span className="text-foreground">MCQ 탭</span>, 점수(AVG@5) 순. 사람 기준선(Human Baseline 83.7%)은 순위 없이 제자리에 표시됩니다.
      </p>
      <DataTable
        label="SimpleBench 순위표"
        columns={columns}
        data={rows}
        getRowId={(r) => `${r.position}`}
        initialSorting={[{ id: "rank", desc: false }]}
        initialLimit={TABLE_ROWS}
        toolbar={
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {`${models}개 모델`}
            <UpdatedNote day={updated} note="가장 최근 추가" />
          </span>
        }
      />
    </div>
  );
}
