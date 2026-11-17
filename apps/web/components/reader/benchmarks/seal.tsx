"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, PercentBar, ProviderDot, ToggleChip, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { providerKey, providerLabel } from "@/components/reader/benchmarks/provider-colors";
import type { SealBoard, SealRow } from "@/lib/benchmark-view";

const TABLE_ROWS = 25;

/** The site sends a company code ("anthropic", "thinkingmachines"); a known maker reads by its name. */
function company(org: string | null): string {
  if (!org) return "—";
  const key = providerKey(org);
  return key === "other" ? org : providerLabel(key);
}

const col = createColumnHelper<SealRow>();

function buildColumns() {
  // labs.scale.com's board table: Rank (UB), model, score ± its confidence interval
  return [
    col.accessor((r) => r.rank ?? undefined, {
      id: "rank",
      header: "순위 (UB)",
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
      meta: { label: "모델" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <ProviderDot provider={r.provider} />
          <span className="max-w-72 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {r.isNew && <span className="rounded bg-primary/10 px-1 text-xs font-bold text-primary">NEW</span>}
        </span>
      ),
    }),
    col.accessor("score", {
      header: "점수 ± 신뢰구간",
      meta: { label: "점수" },
      cell: ({ row: { original: r } }) => {
        const text = `${r.score.toFixed(2)}${r.half !== null ? ` ± ${r.half.toFixed(2)}` : ""}`;
        return (
          <span className="flex items-center gap-2">
            <span className="w-28 font-semibold tabular-nums">{text}</span>
            <PercentBar
              value={r.score}
              low={r.half !== null ? r.score - r.half : null}
              high={r.half !== null ? r.score + r.half : null}
              label={`점수 ${text}`}
            />
          </span>
        );
      },
    }),
    col.accessor((r) => r.org ?? undefined, { id: "org", header: "개발사", meta: { label: "개발사" }, cell: ({ row }) => company(row.original.org) }),
    col.accessor((r) => r.created ?? undefined, { id: "created", header: "등록일", meta: { label: "등록일" }, cell: ({ row }) => row.original.created ?? "—" }),
  ];
}

/**
 * Scale SEAL as labs.scale.com shows a board: a board picker (the boards mirrored from its
 * index, a board's open tab first) and that board's table in the served order, ranked by the
 * site's "Rank (UB)", which ties share, with the score and its confidence interval.
 */
export function SealCard({ boards }: { boards: SealBoard[] }) {
  const [key, setKey] = useState(boards[0]?.key ?? "");
  const board = boards.find((b) => b.key === key) ?? boards[0];
  const columns = useMemo(() => buildColumns(), []);
  if (!board) return null;
  return (
    <div className="space-y-3">
      <div role="group" aria-label="SEAL 벤치마크" className="flex flex-wrap gap-1.5">
        {boards.map((b) => (
          <ToggleChip key={b.key} pressed={b.key === board.key} onClick={() => setKey(b.key)}>
            {b.title}
          </ToggleChip>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        사이트 기본 보기 그대로: <span className="text-foreground">Rank (UB)</span> 순. Rank (UB)는 신뢰구간 하한이 이 모델의 상한보다 높은 모델 수에 1을 더한 값이라 같은 순위가 여럿일 수 있습니다.
      </p>
      <DataTable
        key={board.key}
        label={`Scale SEAL ${board.title} 순위표`}
        columns={columns}
        data={board.rows}
        getRowId={(r) => r.model}
        initialSorting={[]}
        initialLimit={TABLE_ROWS}
        toolbar={
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {`${board.rows.length}개 모델`}
            <UpdatedNote day={board.updated} note="가장 최근 등록 결과" />
            <a href={board.page} target="_blank" rel="noopener noreferrer" className="hover:text-foreground hover:underline">
              labs.scale.com에서 보기
            </a>
          </span>
        }
      />
    </div>
  );
}
