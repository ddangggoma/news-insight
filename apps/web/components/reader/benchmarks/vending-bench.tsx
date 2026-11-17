"use client";

import { useState } from "react";

import { ChangeMark, ProviderDot, UpdatedNote } from "@/components/reader/benchmarks/parts";
import { Button } from "@/components/ui/button";
import { type VendingRow, vendingBalance } from "@/lib/benchmark-view";

/** andonlabs.com lists ten rows, then "Show more". */
const FIRST_ROWS = 10;

/**
 * Vending-Bench 2 as andonlabs.com's "Current leaderboard" shows it: rank, model and the money
 * balance at the end of the simulated year, best first, ten rows and then the rest on request.
 * The bar is the balance against the best one (a balance below zero draws none).
 */
export function VendingBenchCard({ rows, updated }: { rows: VendingRow[]; updated: string | null }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, FIRST_ROWS);
  const best = Math.max(1, ...rows.map((r) => r.balance));
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span>
          사이트 기본 보기 그대로: <span className="text-foreground">실행 평균 최종 잔고</span>가 큰 순 (시작 자금 $500)
        </span>
        <UpdatedNote day={updated} note="가장 최근 공개 모델 기준" />
      </p>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <caption className="sr-only">Vending-Bench 2 순위표</caption>
          <thead className="bg-muted/60 text-xs font-semibold text-muted-foreground">
            <tr>
              <th scope="col" className="h-9 w-14 px-2 text-right">
                순위
              </th>
              <th scope="col" className="px-2 text-left">
                모델
              </th>
              <th scope="col" className="px-2 text-left">
                최종 잔고
              </th>
              <th scope="col" className="hidden px-2 text-left sm:table-cell">
                공개일
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={`${r.rank}|${r.name}`} className="border-b border-border last:border-0 hover:bg-muted/50">
                <td className="px-2 py-2 text-right">
                  <span className="flex items-center justify-end gap-1">
                    <span className="font-semibold tabular-nums">{r.rank}</span>
                    <ChangeMark change={r.change} by={r.changeBy} />
                  </span>
                </td>
                <th scope="row" className="px-2 py-2 text-left font-normal">
                  <span className="flex items-center gap-1.5">
                    <ProviderDot provider={r.provider} />
                    <span className="max-w-64 truncate font-medium" title={r.model}>
                      {r.name}
                    </span>
                    {r.org && <span className="hidden text-xs text-muted-foreground md:inline">{r.org}</span>}
                  </span>
                </th>
                <td className="px-2 py-2">
                  <span className="flex items-center gap-2">
                    <span className="w-24 font-semibold tabular-nums">{vendingBalance(r.balance)}</span>
                    <span role="img" aria-label={`최종 잔고 ${vendingBalance(r.balance)}`} className="relative block h-3 w-24 shrink-0 rounded-sm bg-muted md:w-48">
                      <span className="absolute inset-y-0 left-0 rounded-sm bg-primary/70" style={{ width: `${Math.max(0, Math.min(100, (r.balance / best) * 100))}%` }} aria-hidden />
                    </span>
                  </span>
                </td>
                <td className="hidden px-2 py-2 text-muted-foreground tabular-nums sm:table-cell">{r.released ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{`${rows.length}개 모델 중 ${shown.length}개`}</span>
        {rows.length > FIRST_ROWS && (
          <Button variant="outline" size="sm" onClick={() => setAll(!all)}>
            {all ? "상위 10개만 보기" : "더 보기"}
          </Button>
        )}
        <span>± 오차는 Epoch AI 배포본에 없어 생략했습니다.</span>
      </div>
    </div>
  );
}
