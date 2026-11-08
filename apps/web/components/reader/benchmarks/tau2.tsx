"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, PercentBar, ProviderDot, Segmented, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { TAU2_BOARDS } from "@/lib/benchmark-types";
import type { Tau2Row, Tau2View } from "@/lib/benchmark-view";

type Track = "core" | "banking" | "voice";
const TRACKS: { key: Track; label: string; boards: string[] }[] = [
  { key: "core", label: "τ²-bench", boards: ["overall", "retail", "airline", "telecom"] },
  { key: "banking", label: "τ³-Banking", boards: ["banking_knowledge"] },
  { key: "voice", label: "τ³-Voice (영어)", boards: ["voice"] },
];
const PASS_K = [1, 2, 3, 4] as const;

type Shown = Tau2Row & { shownRank: number; score: number | null };

const col = createColumnHelper<Shown>();

function buildColumns(k: number, banking: boolean) {
  return [
    col.accessor("shownRank", {
      id: "model",
      header: "순위 · 모델",
      meta: { label: "모델" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <span className="w-6 text-right font-semibold tabular-nums">{r.shownRank}</span>
          <ProviderDot provider={r.provider} />
          <span className="max-w-52 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {!r.verified && (
            <span role="img" aria-label="미검증 제출" title="사이트 표기: Unverified submission (검증 정보 부족)" className="text-xs text-amber-700 dark:text-amber-400">
              ⚠ 미검증
            </span>
          )}
          <ChangeMark change={r.change} by={r.changeBy} />
        </span>
      ),
    }),
    col.accessor((r) => r.submitter ?? undefined, { id: "submitter", header: "제출 조직", meta: { label: "제출 조직" }, cell: ({ row }) => row.original.submitter ?? "—" }),
    ...(banking
      ? [col.accessor((r) => r.retrieval ?? undefined, { id: "retrieval", header: "검색 방식", meta: { label: "검색 방식" }, cell: ({ row }) => row.original.retrieval ?? "—" })]
      : []),
    col.accessor((r) => r.effort ?? undefined, { id: "effort", header: "추론 강도", meta: { label: "추론 강도" }, cell: ({ row }) => row.original.effort ?? "—" }),
    col.accessor((r) => r.score ?? undefined, {
      id: "score",
      header: `pass^${k}`,
      meta: { label: `pass^${k}` },
      cell: ({ row: { original: r } }) =>
        r.score === null ? (
          "—"
        ) : (
          <span className="flex items-center gap-2">
            <span className="w-14 font-semibold tabular-nums">{`${r.score.toFixed(1)}%`}</span>
            <PercentBar value={r.score} label={`pass^${k} ${r.score.toFixed(1)}%`} />
          </span>
        ),
    }),
    col.accessor((r) => r.release ?? undefined, { id: "release", header: "모델 공개일", meta: { label: "모델 공개일" }, cell: ({ row }) => row.original.release ?? "—" }),
  ];
}

/** The board's standard submissions ranked by pass^k, best first, a missing score last. */
export function rankTau2(rows: Tau2Row[], k: number): Shown[] {
  const ranked = rows
    .filter((r) => r.rank !== null)
    .map((r) => ({ ...r, score: r.passes[k - 1] ?? null }))
    // the default (pass^1) keeps the collector's order; pass^k re-sorts the same rows, stably
    .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0))
    .sort((a, b) => (a.score === null ? 1 : 0) - (b.score === null ? 1 : 0) || (b.score ?? 0) - (a.score ?? 0));
  return ranked.map((r, index) => ({ ...r, shownRank: index + 1 }));
}

/**
 * τ²-bench as taubench.com shows its tracks: τ²-bench (retail, airline, telecom and their
 * mean), τ³-Banking and τ³-Voice (English), standard submissions only, ranked by pass^1 with a
 * pass^k switch (pass^k: all k tries of a task succeed). Unverified submissions carry the
 * site's warning mark; the submitting organisation is a column.
 */
export function Tau2Table({ view }: { view: Tau2View }) {
  const present = new Set(view.boards);
  const tracks = TRACKS.filter((t) => t.boards.some((b) => present.has(b)));
  const [track, setTrack] = useState<Track>(tracks[0]?.key ?? "core");
  const current = tracks.find((t) => t.key === track) ?? tracks[0];
  const [domain, setDomain] = useState("overall");
  const board = current && current.boards.length > 1 ? (current.boards.includes(domain) ? domain : current.boards[0]) : (current?.boards[0] ?? "overall");
  const [k, setK] = useState(1);
  const passK = track === "voice" ? 1 : k;
  const shown = rankTau2(
    view.rows.filter((r) => r.board === board),
    passK,
  );
  const columns = useMemo(() => buildColumns(passK, board === "banking_knowledge"), [passK, board]);
  const label = TAU2_BOARDS.find((b) => b.key === board);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented label="τ-bench 트랙" options={tracks.map((t) => ({ key: t.key, label: t.label }))} value={track} onChange={(key) => setTrack(key as Track)} />
        {current && current.boards.length > 1 && (
          <Segmented
            label="도메인"
            options={current.boards.filter((b) => present.has(b)).map((key) => ({ key, label: TAU2_BOARDS.find((b) => b.key === key)?.label ?? key }))}
            value={board}
            onChange={setDomain}
          />
        )}
        {track !== "voice" && <Segmented label="pass^k" options={PASS_K.map((n) => ({ key: String(n), label: `pass^${n}` }))} value={String(k)} onChange={(key) => setK(Number(key))} />}
        <UpdatedNote day={view.updated[board]} note="최근 제출일" />
      </div>
      <DataTable
        key={`${board}|${passK}`}
        label={`τ²-bench ${label ? `${label.track} ${label.label}` : board} 순위표`}
        columns={columns}
        data={shown}
        getRowId={(r) => r.id}
        initialSorting={[{ id: "model", desc: false }]}
        initialLimit={25}
        toolbar={<span className="text-xs text-muted-foreground">{`표준 제출 ${shown.length}개 · 사용자 시뮬레이터가 모델과 대화`}</span>}
      />
    </div>
  );
}
