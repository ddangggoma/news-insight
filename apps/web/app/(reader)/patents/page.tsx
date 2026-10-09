import type { Metadata } from "next";
import Link from "next/link";

import { StoryRow } from "@/components/reader/story-row";
import { Sparkline } from "@/components/reader/sparkline";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { param, pageParam, type SearchParams } from "@/lib/params";
import { changeLabel, type PatentTrend, type PatentView } from "@/lib/patent-types";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "특허 신호", robots: { index: false } };

function TrendTable({ title, rows, href, periodLabel }: { title: string; rows: PatentTrend[]; href: (row: PatentTrend) => string; periodLabel: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-base">{title}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length ? (
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="py-1 text-left font-normal">이름</th>
                <th className="py-1 text-right font-normal">{periodLabel}</th>
                <th className="py-1 text-right font-normal">변화</th>
                <th className="py-1 text-right font-normal">추이</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-t">
                  <td className="py-1.5">
                    <Link href={href(row)} className="hover:underline">
                      {row.label}
                    </Link>
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{row.current}</td>
                  <td className="py-1.5 text-right text-xs tabular-nums text-muted-foreground">{changeLabel(row.current, row.previous)}</td>
                  <td className="py-1.5 text-right">
                    <Sparkline values={row.counts} label={`${row.label} 추이`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground">아직 집계할 특허 카드가 없습니다.</p>
        )}
      </CardContent>
    </Card>
  );
}

export default async function PatentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const kind = param(sp, "kind") === "quarter" ? "quarter" : "month";
  const page = pageParam(sp);
  const view = await readerGet<PatentView>("/patents", { kind, page }, REVALIDATE.feed);
  const peak = Math.max(1, ...view.periods.map((p) => p.total));
  const periodLabel = kind === "quarter" ? "이번 분기" : "이번 달";
  const pages = Math.max(1, Math.ceil(view.recent.total / view.recent.size));
  const total = view.periods.reduce((sum, p) => sum + p.total, 0);

  return (
    <main className="mx-auto max-w-5xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">특허 신호</h1>
          <p className="text-sm text-muted-foreground">
            특허 공보(EPO OPS로 미국·유럽·중국)와 지식재산으로 분류된 기사를 기술 분야·기업별로 셉니다. 공보 수집은 EPO OPS 무료 키가 .env에 있을 때만 동작합니다.
          </p>
        </div>
        <nav aria-label="집계 단위" className="flex rounded-md border p-0.5 text-sm">
          {(["month", "quarter"] as const).map((k) => (
            <Link key={k} href={`/patents?kind=${k}`} aria-current={kind === k ? "page" : undefined} className={cn("rounded px-3 py-1", kind === k ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
              {k === "month" ? "월별" : "분기별"}
            </Link>
          ))}
        </nav>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-base">
              {kind === "quarter" ? "분기별" : "월별"} 특허 신호 ({total}건)
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-32 items-end gap-1" role="img" aria-label="기간별 특허 신호 수">
            {view.periods.map((p) => (
              <div key={p.key} className="flex flex-1 flex-col items-center gap-1" title={`${p.key}: ${p.total}건 (특허청 ${p.office}건)`}>
                <div className="flex w-full flex-col-reverse overflow-hidden rounded-t" style={{ height: `${Math.max(2, (p.total / peak) * 104)}px` }}>
                  <div className="bg-primary" style={{ height: `${p.total ? (p.office / p.total) * 100 : 0}%` }} />
                  <div className="flex-1 bg-primary/40" />
                </div>
                <span className="text-[10px] tabular-nums text-muted-foreground">{p.key.slice(2)}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">진한 부분: 특허청 수집 · 옅은 부분: 지식재산 기사</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <TrendTable title="기술 분야" rows={view.nodes} periodLabel={periodLabel} href={(row) => `/?${row.axis}=${encodeURIComponent(row.key)}&signal=ip&period=30d`} />
        <TrendTable title="기업" rows={view.companies} periodLabel={periodLabel} href={(row) => `/?company=${encodeURIComponent(row.key)}&signal=ip&period=30d`} />
      </div>

      <section aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="text-base font-semibold">
          최근 특허 신호
        </h2>
        {view.recent.items.length ? (
          view.recent.items.map((item) => <StoryRow key={item.id} item={item} />)
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">해당 기간의 특허 신호가 없습니다.</p>
        )}
        {pages > 1 ? (
          <nav aria-label="페이지" className="flex items-center justify-center gap-4 pt-2 text-sm">
            {page > 1 ? <Link href={`/patents?kind=${kind}&page=${page - 1}`}>← 이전</Link> : <span className="text-muted-foreground">← 이전</span>}
            <span className="tabular-nums text-muted-foreground">
              {page} / {pages}
            </span>
            {page < pages ? <Link href={`/patents?kind=${kind}&page=${page + 1}`}>다음 →</Link> : <span className="text-muted-foreground">다음 →</span>}
          </nav>
        ) : null}
      </section>
    </main>
  );
}
