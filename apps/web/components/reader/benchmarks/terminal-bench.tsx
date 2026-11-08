"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, PercentBar, ProviderDot, Segmented, ToggleChip, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { type TbRow, type TbView, tbCost, tbTokens } from "@/lib/benchmark-view";

const TABLE_ROWS = 25;
type Efforts = "best" | "all";

/** "2026-09-22" → "2026-09-22" (tbench.ai prints "Sep 22, 2026"; the reader keeps ISO days). */
const day = (iso: string | null) => iso ?? "—";

const col = createColumnHelper<TbRow & { shownRank: number | null }>();

function buildColumns() {
  // tbench.ai's own column order: rank, model (effort in brackets), agent, accuracy ± CI, date,
  // tokens, cost
  return [
    col.accessor((r) => r.shownRank ?? undefined, {
      id: "rank",
      header: "순위",
      meta: { label: "순위", numeric: true },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center justify-end gap-1">
          <span className="font-semibold tabular-nums">{r.shownRank ?? "—"}</span>
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
          <span className="max-w-56 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {r.effort ? <span className="text-muted-foreground">({r.effort})</span> : null}
        </span>
      ),
    }),
    col.accessor("agent", { header: "에이전트", meta: { label: "에이전트" }, cell: ({ row }) => row.original.agent }),
    col.accessor("accuracy", {
      header: "정확도 (95% CI)",
      meta: { label: "정확도" },
      cell: ({ row: { original: r } }) => {
        const half = r.high !== null ? r.high - r.accuracy : null;
        const text = `${r.accuracy.toFixed(1)}%${half !== null ? ` ± ${half.toFixed(1)}%` : ""}`;
        return (
          <span className="flex items-center gap-2">
            <span className="w-28 font-semibold tabular-nums">{text}</span>
            <PercentBar value={r.accuracy} low={r.low} high={r.high} label={`정확도 ${text}`} />
          </span>
        );
      },
    }),
    col.accessor((r) => r.date ?? undefined, { id: "date", header: "공개일", meta: { label: "공개일" }, cell: ({ row }) => day(row.original.date) }),
    col.accessor((r) => r.tokens ?? undefined, { id: "tokens", header: "토큰", meta: { label: "토큰", numeric: true }, cell: ({ row }) => tbTokens(row.original.tokens) }),
    col.accessor((r) => r.cost ?? undefined, { id: "cost", header: "비용", meta: { label: "비용", numeric: true }, cell: ({ row }) => tbCost(row.original.cost) }),
  ];
}

/** The best row of each agent on the board, best first: the harness comparison. */
export function bestByAgent(rows: TbRow[]): TbRow[] {
  const best = new Map<string, TbRow>();
  for (const row of rows) if ((best.get(row.agent)?.accuracy ?? -1) < row.accuracy) best.set(row.agent, row);
  return [...best.values()].sort((a, b) => b.accuracy - a.accuracy);
}

function AgentSummary({ rows }: { rows: TbRow[] }) {
  const best = bestByAgent(rows);
  if (best.length === 0) return null;
  return (
    <figure className="space-y-2 rounded-lg border bg-muted/30 px-3 py-3">
      <figcaption className="text-sm font-medium">에이전트별 최고 점수</figcaption>
      <ul aria-label="에이전트별 최고 점수" className="space-y-1.5">
        {best.map((r) => (
          <li key={r.agent} className="grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-2 text-sm">
            <span className="truncate font-medium" title={r.agent}>
              {r.agent}
            </span>
            <span className="flex min-w-0 items-center gap-2">
              <span className="relative block h-3 min-w-0 flex-1 rounded-sm bg-muted" aria-hidden>
                <span className="absolute inset-y-0 left-0 rounded-sm bg-primary/70" style={{ width: `${Math.min(100, r.accuracy)}%` }} />
              </span>
              <span className="hidden max-w-40 truncate text-xs text-muted-foreground sm:inline" title={`${r.model}${r.effort ? ` (${r.effort})` : ""}`}>
                {`${r.model}${r.effort ? ` (${r.effort})` : ""}`}
              </span>
            </span>
            <span className="font-semibold tabular-nums">{`${r.accuracy.toFixed(1)}%`}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/**
 * Terminal-Bench as tbench.ai opens it: the 4.0 board, one row per model and agent (its best
 * effort), ranked with ties shared, resolution rate with its 95% interval. A board toggle (4.0 /
 * 3.0 / 2.1), the site's "all efforts" switch, a filter chip per agent (built from the data) and,
 * above the table, the best score each agent reached.
 */
export function TerminalBenchCard({ view }: { view: TbView }) {
  const [board, setBoard] = useState(view.boards[0] ?? "4.0");
  const [efforts, setEfforts] = useState<Efforts>("best");
  const [agent, setAgent] = useState<string | null>(null);
  const columns = useMemo(() => buildColumns(), []);

  const onBoard = view.rows.filter((r) => r.board === board);
  const best = onBoard.filter((r) => r.rank !== null);
  const pool = efforts === "best" ? best : onBoard;
  // agents in order of their best score on the board
  const agents = bestByAgent(onBoard).map((r) => r.agent);
  const shown = pool
    .filter((r) => agent === null || r.agent === agent)
    .map((r) => ({ ...r, shownRank: efforts === "best" ? r.rank : r.allRank }))
    .sort((a, b) => (a.shownRank ?? Infinity) - (b.shownRank ?? Infinity));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="Terminal-Bench 버전"
          options={view.boards.map((key) => ({ key, label: `TB ${key}` }))}
          value={board}
          onChange={(key) => {
            setBoard(key);
            setAgent(null);
          }}
        />
        <Segmented
          label="추론 강도 행"
          options={[
            { key: "best", label: "모델·에이전트별 최고 강도" },
            { key: "all", label: "모든 강도" },
          ]}
          value={efforts}
          onChange={(key) => setEfforts(key as Efforts)}
        />
        <UpdatedNote day={view.updated[board]} note="사이트 기본: 최고 강도만" />
      </div>
      <AgentSummary rows={best} />
      <div role="group" aria-label="에이전트별" className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs font-medium text-muted-foreground">에이전트별</span>
        <ToggleChip pressed={agent === null} onClick={() => setAgent(null)}>
          전체
        </ToggleChip>
        {agents.map((name) => (
          <ToggleChip key={name} pressed={agent === name} onClick={() => setAgent(agent === name ? null : name)}>
            {name}
          </ToggleChip>
        ))}
      </div>
      <DataTable
        key={`${board}|${efforts}`}
        label={`Terminal-Bench ${board} 순위표`}
        columns={columns}
        data={shown}
        getRowId={(r) => r.id}
        initialSorting={[{ id: "rank", desc: false }]}
        initialLimit={TABLE_ROWS}
        emptyText="이 조건에 맞는 행이 없습니다"
        toolbar={<span className="text-xs text-muted-foreground">{`${shown.length}개 조합`}</span>}
      />
    </div>
  );
}
