"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, ProviderDot, ToggleChip } from "@/components/reader/benchmarks/parts";
import { providerKey, providerLabel } from "@/components/reader/benchmarks/provider-colors";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type BenchmarkRow, type BenchmarkSite, boardLabel, extraNumber, extraString } from "@/lib/benchmark-types";
import { formatNumber } from "@/lib/format";

interface ArenaRow {
  id: string;
  row: BenchmarkRow;
  rank: number | null;
  model: string;
  org: string | null;
  score: number;
  low: number | null;
  high: number | null;
  votes: number | null;
  license: string | null;
}

/** The agent board scores a share of tasks (0-1); the others are Elo-style ratings. */
const isShare = (board: string) => board === "agent";

function toArena(row: BenchmarkRow, index: number): ArenaRow {
  return {
    id: `${row.model}|${index}`,
    row,
    rank: extraNumber(row, "rank") ?? row.rank,
    model: row.model,
    org: row.org,
    score: row.value,
    low: row.ci_low,
    high: row.ci_high,
    votes: extraNumber(row, "vote_count") ?? extraNumber(row, "session_count"),
    license: extraString(row, "license"),
  };
}

const isOpenLicense = (license: string | null) => license !== null && !/proprietary/i.test(license);

function orgName(org: string | null): string {
  if (!org) return "—";
  const key = providerKey(org);
  return key === "other" ? org : providerLabel(key);
}

/** The 95% interval as a segment on the board's own min–max scale, the score as a tick. */
function IntervalBar({ low, high, score, min, max, format }: { low: number | null; high: number | null; score: number; min: number; max: number; format: (v: number) => string }) {
  const span = max - min || 1;
  const at = (v: number) => `${(((v - min) / span) * 100).toFixed(2)}%`;
  const label = low !== null && high !== null ? `95% 신뢰구간 ${format(low)}–${format(high)}` : "95% 신뢰구간 정보 없음";
  return (
    <span className="flex items-center gap-2">
      <span role="img" aria-label={label} className="relative block h-3 w-24 shrink-0 md:w-32">
        <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" aria-hidden />
        {low !== null && high !== null && (
          <span
            className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-primary/35"
            style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }}
            aria-hidden
          />
        )}
        <span className="absolute top-1/2 h-3 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: at(score) }} aria-hidden />
      </span>
      {low !== null && high !== null && (
        <span className="text-[11px] text-muted-foreground tabular-nums">{`+${format(high - score)} / −${format(score - low)}`}</span>
      )}
    </span>
  );
}

const col = createColumnHelper<ArenaRow>();

function buildColumns(board: string, min: number, max: number) {
  const share = isShare(board);
  const format = share ? (v: number) => (v * 100).toFixed(1) : (v: number) => v.toFixed(0);
  return [
    col.accessor((r) => r.rank ?? undefined, {
      id: "model",
      header: "순위 · 모델",
      meta: { label: "모델" },
      cell: ({ row: { original: r } }) => (
        <span className="flex items-center gap-1.5">
          <span className="w-6 text-right font-semibold tabular-nums">{r.rank ?? "—"}</span>
          <ProviderDot org={r.org} />
          <span className="max-w-56 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          <ChangeMark change={r.row.change} by={r.row.change_by} />
        </span>
      ),
    }),
    col.accessor("score", {
      header: share ? "점수(%)" : "점수",
      meta: { label: "점수", numeric: true },
      cell: ({ getValue }) => <span className="font-semibold">{format(getValue())}</span>,
    }),
    col.accessor((r) => (r.low !== null && r.high !== null ? r.high - r.low : undefined), {
      id: "ci",
      header: "95% CI",
      meta: { label: "95% CI" },
      cell: ({ row: { original: r } }) => <IntervalBar low={r.low} high={r.high} score={r.score} min={min} max={max} format={format} />,
    }),
    col.accessor((r) => r.votes ?? undefined, {
      id: "votes",
      header: share ? "세션 수" : "투표 수",
      meta: { label: share ? "세션 수" : "투표 수", numeric: true },
      cell: ({ row }) => (row.original.votes === null ? "—" : formatNumber(row.original.votes)),
    }),
    col.accessor((r) => orgName(r.org), { id: "org", header: "조직", meta: { label: "조직" } }),
    col.accessor((r) => r.license ?? undefined, { id: "license", header: "라이선스", meta: { label: "라이선스" }, cell: ({ row }) => row.original.license ?? "—" }),
  ];
}

/**
 * LMArena's leaderboard: one tab per board, rank · model · score · 95% interval (drawn on the
 * board's own range so overlapping intervals read as ties) · votes · organisation · licence,
 * with an open-licence filter and a name search.
 */
export function LmArenaTable({ site }: { site: BenchmarkSite }) {
  const boards = site.boards.filter((b) => site.rows.some((r) => r.board === b));
  const [board, setBoard] = useState(boards[0] ?? "");
  const [openOnly, setOpenOnly] = useState(false);
  const [query, setQuery] = useState("");

  const rows = useMemo(() => site.rows.filter((r) => r.board === board).map(toArena), [site.rows, board]);
  const min = Math.min(...rows.map((r) => r.low ?? r.score));
  const max = Math.max(...rows.map((r) => r.high ?? r.score));
  const columns = useMemo(() => buildColumns(board, min, max), [board, min, max]);
  const needle = query.trim().toLowerCase();
  const shown = rows.filter((r) => (!openOnly || isOpenLicense(r.license)) && (!needle || r.model.toLowerCase().includes(needle)));
  const published = rows.map((r) => extraString(r.row, "leaderboard_publish_date")).find(Boolean);

  return (
    <div className="space-y-3">
      <Tabs value={board} onValueChange={setBoard}>
        <div className="overflow-x-auto">
          <TabsList>
            {boards.map((b) => (
              <TabsTrigger key={b} value={b} className="px-3">
                {boardLabel("lmarena", b)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
      </Tabs>
      <DataTable
        key={board}
        label={`LMArena ${boardLabel("lmarena", board)} 순위표`}
        columns={columns}
        data={shown}
        getRowId={(r) => r.id}
        initialSorting={[{ id: "model", desc: false }]}
        toolbar={
          <>
            <Input type="search" aria-label="모델 검색" placeholder="모델 검색" value={query} onChange={(event) => setQuery(event.target.value)} className="h-7 w-40 text-xs" />
            <ToggleChip pressed={openOnly} onClick={() => setOpenOnly((v) => !v)}>
              오픈 라이선스만
            </ToggleChip>
            <span className="text-xs text-muted-foreground">
              {`${shown.length}개 모델`}
              {published && ` · 보드 공개 ${published}`}
            </span>
          </>
        }
      />
    </div>
  );
}
