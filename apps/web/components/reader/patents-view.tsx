import { AppLink as Link } from "@/components/app-link";

import { CountChange, RankBars, StatStrip } from "@/components/reader/insight-parts";
import { PatentCard } from "@/components/reader/patent-card";
import { PatentPeriods } from "@/components/reader/patent-charts";
import { Legend, Panel } from "@/components/reader/radar/parts";
import { formatNumber } from "@/lib/format";
import { type PatentTrend, type PatentView, patentSummary, periodLabel } from "@/lib/patent-types";
import { cn } from "@/lib/utils";

function trendRows(rows: PatentTrend[], href: (row: PatentTrend) => string, periodName: string) {
  // the API ranks by the last three periods: the bar shows that sum, so length follows rank
  return rows.slice(0, 8).map((row) => ({
    key: row.key,
    label: row.label,
    href: href(row),
    value: row.counts.slice(-3).reduce((a, b) => a + b, 0),
    display: `${row.counts.slice(-3).reduce((a, b) => a + b, 0)}건`,
    trend: row.counts,
    change: <CountChange current={row.current} previous={row.previous} />,
    sub: `${periodName} ${row.current}건, 직전 ${row.previous}건, 전체 ${row.counts.reduce((a, b) => a + b, 0)}건`,
  }));
}

function signed(value: number): string {
  return value > 0 ? `+${formatNumber(value)}` : value < 0 ? `−${formatNumber(-value)}` : "±0";
}

/** The 특허 신호 page body for one API view (the page fetches it; previews pass fixtures). */
export function PatentsView({ view, kind, page }: { view: PatentView; kind: "month" | "quarter"; page: number }) {
  const unitName = kind === "quarter" ? "분기" : "달";
  const periodName = kind === "quarter" ? "이번 분기" : "이번 달";
  const pages = Math.max(1, Math.ceil(view.recent.total / view.recent.size));
  const summary = patentSummary(view);
  const { current, previous } = summary;
  const diff = current && previous ? current.total - previous.total : null;
  const exploreHref = (filter: string) => `/?${filter}&signal=ip&period=30d`;

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
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

      <StatStrip
        stats={[
          {
            label: `${periodName} (진행 중)`,
            value: formatNumber(current?.total ?? 0),
            unit: "건",
            note: current ? `${periodLabel(current.key)}, 특허청 ${current.office}건` : undefined,
          },
          {
            label: `지난 ${unitName} 대비`,
            value: diff === null ? "–" : signed(diff),
            unit: diff === null ? undefined : "건",
            note: previous ? `지난 ${unitName} ${previous.total}건${summary.change !== null ? `, ${summary.change >= 0 ? "+" : ""}${Math.round(summary.change * 100)}%` : ""}` : undefined,
          },
          {
            label: "특허청 공보 비중",
            value: summary.officeShare === null ? "–" : `${Math.round(summary.officeShare * 100)}`,
            unit: summary.officeShare === null ? undefined : "%",
            note: `공보 ${formatNumber(summary.office)}건, 기사 ${formatNumber(summary.total - summary.office)}건`,
          },
          {
            label: "가장 많이 늘어난 곳",
            value: summary.riser ? `+${summary.riser.current - summary.riser.previous}` : "–",
            unit: summary.riser ? "건" : undefined,
            note: summary.riser ? summary.riser.label : "직전 기간보다 늘어난 분야·기업 없음",
          },
        ]}
      />

      <Panel
        id="patent-periods"
        title={`${kind === "quarter" ? "분기별" : "월별"} 특허 신호 (${formatNumber(summary.total)}건)`}
        question={`최근 ${view.periods.length}개 ${unitName}입니다. 마지막 막대(옅은 색)는 아직 진행 중인 ${unitName}입니다.`}
      >
        {summary.total ? (
          <>
            <PatentPeriods periods={view.periods} />
            <Legend
              className="mt-2"
              items={[
                { label: "특허청 공보", swatch: "var(--cat-1)" },
                { label: "지식재산 기사", swatch: "var(--cat-2)" },
              ]}
            />
          </>
        ) : (
          <p className="py-16 text-center text-sm text-muted-foreground">아직 집계할 특허 신호가 없습니다.</p>
        )}
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel id="patent-fields" title="기술 분야" question={`막대는 최근 3개 ${unitName} 건수, ▲▼는 지난 ${unitName} 대비, 오른쪽은 ${view.periods.length}개 ${unitName} 추이입니다.`}>
          <RankBars empty="아직 집계할 특허 카드가 없습니다." rows={trendRows(view.nodes, (row) => exploreHref(`${row.axis}=${encodeURIComponent(row.key)}`), periodName)} />
        </Panel>
        <Panel id="patent-companies" title="기업" question={`특허 신호에 등장한 등록 기업입니다. 막대는 최근 3개 ${unitName} 건수입니다.`}>
          <RankBars empty="아직 기업이 언급된 특허 신호가 없습니다." rows={trendRows(view.companies, (row) => exploreHref(`company=${encodeURIComponent(row.key)}`), periodName)} />
        </Panel>
      </div>

      <section aria-labelledby="recent-heading" className="space-y-3 pt-2">
        <h2 id="recent-heading" className="text-base font-semibold">
          최근 특허 신호 <span className="text-sm font-normal text-muted-foreground">({formatNumber(view.recent.total)}건)</span>
        </h2>
        {view.recent.items.length ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {view.recent.items.map((item) => (
              <PatentCard key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border py-10 text-center text-sm text-muted-foreground">해당 기간의 특허 신호가 없습니다.</p>
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
