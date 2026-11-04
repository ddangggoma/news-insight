import { AppLink as Link } from "@/components/app-link";

import { DealCard } from "@/components/reader/deal-card";
import { DealTimeline } from "@/components/reader/deal-charts";
import { RankBars, StatStrip } from "@/components/reader/insight-parts";
import { Legend, Panel } from "@/components/reader/radar/parts";
import {
  DEAL_KIND_LABEL,
  DEAL_SERIES,
  DEAL_SERIES_COLOR,
  DEAL_SERIES_LABEL,
  type DealKind,
  type DealParty,
  type DealView,
  dealBuckets,
  dealSeries,
  formatUsd,
  formatUsdShort,
} from "@/lib/deal-types";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export const DEAL_DAYS = [30, 90, 180, 365];

function href(query: { days: number; kind?: string; company?: string }): string {
  const params = new URLSearchParams({ days: String(query.days) });
  if (query.kind) params.set("kind", query.kind);
  if (query.company) params.set("company", query.company);
  return `/deals?${params.toString()}`;
}

function PartyLink({ name, companyKey, days }: { name: string; companyKey: string | null; days: number }) {
  return companyKey ? (
    <Link href={href({ days, company: companyKey })} className="font-medium hover:text-primary hover:underline">
      {name}
    </Link>
  ) : (
    <span>{name}</span>
  );
}

function kindMix(party: DealParty): string {
  return Object.entries(party.kinds)
    .map(([k, n]) => `${DEAL_KIND_LABEL[k as DealKind]} ${n}`)
    .join(", ");
}

/** The 투자·제휴 page body for one API view (the page fetches it; previews pass fixtures). */
export function DealsView({ view, days, kind, company }: { view: DealView; days: number; kind?: DealKind; company?: string }) {
  const companyName = company ? view.parties.find((p) => p.key === company)?.name ?? company : null;

  const stats = view.stats;
  const sized = stats?.sized ?? view.kinds.reduce((sum, k) => sum + k.sized, 0);
  const usd = stats?.usd ?? view.kinds.reduce((sum, k) => sum + k.usd, 0);
  const { unit, buckets } = dealBuckets(view);
  const present = DEAL_SERIES.filter((s) => buckets.some((b) => b.counts[s] > 0));
  const periodName = days === 365 ? "1년" : `${days}일`;
  const partyHref = (key: string | null) => (key ? href({ days, company: key }) : undefined);
  const kindRows = [...view.kinds].sort((a, b) => b.count - a.count);

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <h1 className="text-xl font-semibold">투자·제휴{companyName ? ` · ${companyName}` : ""}</h1>
          <p className="text-sm text-muted-foreground">
            카드에서 로컬 모델이 밤마다 뽑은 투자·인수·제휴·상장·합작·라이선스입니다. 금액의 달러 환산은 고정 환율에 따른 어림값입니다.
          </p>
        </div>
        <nav aria-label="기간" className="flex rounded-md border p-0.5 text-sm">
          {DEAL_DAYS.map((d) => (
            <Link key={d} href={href({ days: d, kind, company })} aria-current={days === d ? "page" : undefined} className={cn("rounded px-2.5 py-1", days === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
              {d === 365 ? "1년" : `${d}일`}
            </Link>
          ))}
        </nav>
      </div>

      <div className="flex flex-wrap gap-2" aria-label="유형">
        <Link href={href({ days, company })} aria-current={!kind ? "page" : undefined} className={cn("rounded-full border px-3 py-1 text-sm", !kind && "border-primary bg-primary/10")}>
          전체 {kind ? "" : view.total}
        </Link>
        {(Object.keys(DEAL_KIND_LABEL) as DealKind[]).map((k) => {
          const count = view.kinds.find((c) => c.kind === k);
          return (
            <Link key={k} href={href({ days, kind: k, company })} aria-current={kind === k ? "page" : undefined} className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm", kind === k && "border-primary bg-primary/10")}>
              <span aria-hidden className="size-2 rounded-full" style={{ background: DEAL_SERIES_COLOR[dealSeries(k)] }} />
              {DEAL_KIND_LABEL[k]} {count ? count.count : 0}
            </Link>
          );
        })}
        {company ? (
          <Link href={href({ days, kind })} className="rounded-full border border-dashed px-3 py-1 text-sm text-muted-foreground">
            기업 필터 해제
          </Link>
        ) : null}
      </div>

      <StatStrip
        stats={[
          { label: `최근 ${periodName} 거래`, value: formatNumber(view.total), unit: "건", note: view.total ? `금액 공개 ${sized}건` : "추출된 거래 없음" },
          { label: "공개 금액 합계", value: formatUsdShort(usd), unit: usd ? "달러" : undefined, note: stats?.outliers ? `500억 달러 이상 ${stats.outliers}건은 오독 의심으로 제외` : stats?.max_usd ? `최대 ${formatUsd(stats.max_usd)}` : "금액이 밝혀진 거래 기준" },
          {
            label: "중앙 금액",
            value: formatUsdShort(stats?.median_usd),
            unit: stats?.median_usd ? "달러" : undefined,
            note: stats?.mean_usd ? `평균 ${formatUsd(stats.mean_usd)}` : "금액 공개 거래가 없음",
          },
          { label: "참여 기업", value: formatNumber(stats?.companies ?? view.parties.length), unit: "곳", note: stats ? `기업 쌍 ${formatNumber(stats.pairs)}개` : undefined },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel
          id="deal-trend"
          title={`${unit === "week" ? "주별" : "월별"} 거래 추이`}
          question={unit === "week" ? "발표일이 속한 주(월요일 시작)로 셉니다. 발표일이 없으면 근거 기사 날짜를 씁니다." : "발표일이 속한 달로 셉니다. 발표일이 없으면 근거 기사 날짜를 씁니다."}
        >
          {view.total ? (
            <>
              <DealTimeline buckets={buckets} unit={unit} series={present} />
              <Legend className="mt-2" items={present.map((s) => ({ label: DEAL_SERIES_LABEL[s], swatch: DEAL_SERIES_COLOR[s] }))} />
            </>
          ) : (
            <p className="py-16 text-center text-sm text-muted-foreground">이 기간에 집계할 거래가 없습니다.</p>
          )}
        </Panel>
        <Panel id="deal-mix" title="유형 구성" question="유형별 건수와 공개된 금액의 합입니다. 누르면 그 유형만 봅니다.">
          <RankBars
            empty="거래가 없습니다."
            rows={kindRows.map((k) => ({
              key: k.kind,
              label: DEAL_KIND_LABEL[k.kind],
              href: href({ days, kind: kind === k.kind ? undefined : k.kind, company }),
              value: k.count,
              display: `${k.count}건`,
              color: DEAL_SERIES_COLOR[dealSeries(k.kind)],
              sub: k.sized ? `${formatUsd(k.usd)} (금액 공개 ${k.sized}건)` : "금액 공개 없음",
            }))}
          />
        </Panel>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Panel id="deal-parties" title="활발한 기업" question="거래 건수 순, 투자자와 대상 모두 셉니다.">
          <RankBars
            empty="아직 추출된 거래가 없습니다."
            rows={view.parties.slice(0, 8).map((p) => ({
              key: p.key ?? p.name,
              label: p.name,
              href: partyHref(p.key),
              value: p.count,
              display: `${p.count}건`,
              sub: [kindMix(p), p.usd ? formatUsd(p.usd) : ""].filter(Boolean).join(" / "),
            }))}
          />
        </Panel>
        <Panel id="deal-sizes" title="금액 상위 기업" question="공개된 거래 금액(달러 환산)의 합 순입니다.">
          <RankBars
            empty="금액이 밝혀진 거래가 아직 없습니다."
            rows={(view.top_usd ?? [...view.parties].filter((p) => p.usd > 0).sort((a, b) => b.usd - a.usd)).slice(0, 8).map((p) => ({
              key: p.key ?? p.name,
              label: p.name,
              href: partyHref(p.key),
              value: p.usd,
              display: formatUsdShort(p.usd),
              color: "var(--cat-1)",
              sub: `${p.count}건, ${kindMix(p)}`,
            }))}
          />
        </Panel>
        <Panel id="deal-pairs" title="기업 간 관계" question="상대가 밝혀진 거래의 주체 → 상대입니다." className="md:col-span-2 lg:col-span-1">
          {view.pairs.length ? (
            <ul className="divide-y text-sm">
              {view.pairs.slice(0, 10).map((p) => (
                <li key={`${p.actor}-${p.counterparty}`} className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 py-1.5">
                  <PartyLink name={p.actor} companyKey={p.actor_key} days={days} />
                  <span aria-hidden className="text-muted-foreground">
                    →
                  </span>
                  <PartyLink name={p.counterparty} companyKey={p.counterparty_key} days={days} />
                  <span className="ml-auto text-xs text-muted-foreground">
                    {p.kinds.map((k) => DEAL_KIND_LABEL[k]).join(", ")}
                    {p.count > 1 ? ` ${p.count}건` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="py-6 text-center text-sm text-muted-foreground">상대가 밝혀진 거래가 아직 없습니다.</p>
          )}
        </Panel>
      </div>

      <section aria-labelledby="deal-list" className="space-y-3 pt-2">
        <h2 id="deal-list" className="text-base font-semibold">
          거래 ({view.total}건{view.total > view.deals.length ? `, 최근 ${view.deals.length}건 표시` : ""})
        </h2>
        {view.deals.length ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {view.deals.map((d) => (
              <DealCard key={d.id} deal={d} companyHref={(key) => href({ days, company: key })} />
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border py-10 text-center text-sm text-muted-foreground">
            해당 조건의 거래가 없습니다. 추출은 매일 밤 00~06시에 로컬 모델이 진행합니다.
          </p>
        )}
      </section>
    </main>
  );
}
