"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/reader/benchmarks/data-table";
import { ChangeMark, ProviderDot, ToggleChip } from "@/components/reader/benchmarks/parts";
import { type ProviderKey, providerKey, providerLabel } from "@/components/reader/benchmarks/provider-colors";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { boardLabel, colourOrg, isOpenLicense } from "@/lib/benchmark-types";
import type { ArenaRow as Projected, ArenaView } from "@/lib/benchmark-view";
import { formatNumber } from "@/lib/format";

/** The agent board scores a share of tasks (0-1); the others are Elo-style ratings. */
const isShare = (board: string) => board === "agent";
const TABLE_ROWS = 25;

/** A projected row plus what the client derives from it (kept out of the page payload). */
type ArenaRow = Projected & { provider: ProviderKey; open: boolean };

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
          <ProviderDot provider={r.provider} />
          <span className="max-w-56 truncate font-medium" title={r.model}>
            {r.model}
          </span>
          {r.open && <span className="rounded border border-emerald-600/40 px-1 text-[10px] text-emerald-700 dark:text-emerald-400">open</span>}
          <ChangeMark change={r.change ?? null} by={r.changeBy ?? 0} />
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
export function LmArenaTable({ view }: { view: ArenaView }) {
  // opens on 텍스트 like the site; boards arrive in the site's tab order
  const [board, setBoard] = useState(view[0]?.key ?? "");
  const [openOnly, setOpenOnly] = useState(false);
  const [query, setQuery] = useState("");

  const current = view.find((b) => b.key === board);
  const rows = useMemo(
    () => (current?.rows ?? []).map((r): ArenaRow => ({ ...r, provider: providerKey(colourOrg(r.org, r.model)), open: isOpenLicense(r.license) })),
    [current],
  );
  const min = Math.min(...rows.map((r) => r.low ?? r.score));
  const max = Math.max(...rows.map((r) => r.high ?? r.score));
  const columns = useMemo(() => buildColumns(board, min, max), [board, min, max]);
  const needle = query.trim().toLowerCase();
  const shown = rows.filter((r) => (!openOnly || r.open) && (!needle || r.model.toLowerCase().includes(needle)));
  const published = current?.published;

  return (
    <div className="space-y-3">
      <Tabs value={board} onValueChange={setBoard}>
        <div className="overflow-x-auto">
          <TabsList>
            {view.map(({ key }) => (
              <TabsTrigger key={key} value={key} className="px-3">
                {boardLabel("lmarena", key)}
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
        getRowId={(r) => r.model}
        initialSorting={[{ id: "model", desc: false }]}
        initialLimit={TABLE_ROWS}
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
