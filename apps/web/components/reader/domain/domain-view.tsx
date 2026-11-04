import { AppLink as Link } from "@/components/app-link";
import { Panel } from "@/components/reader/radar/parts";
import { RankBars, StatStrip } from "@/components/reader/insight-parts";
import { FieldMixBars, SeriesChart } from "@/components/reader/domain/charts";
import { CompanyTable, type RankRow } from "@/components/reader/domain/company-table";
import { FieldsBody } from "@/components/reader/domain/fields-tab";
import {
  ChangeBadge,
  ChipRow,
  DocList,
  DomainTabs,
  EmptyNote,
  HeatmapTable,
  InsightBlock,
  Pager,
  PeriodSelect,
  Segments,
  WatchedBadge,
  fieldChips,
} from "@/components/reader/domain/parts";
import { SeriesTable } from "@/components/reader/domain/series-table";
import { formatNumber } from "@/lib/format";
import {
  type CompaniesTab,
  DOMAIN_META,
  type DocumentsTab,
  type DomainState,
  type DomainView,
  ENTITY_LABEL,
  type OverviewTab,
  type TrendsTab,
  domainHref,
  kpiStats,
  orgTypeLabel,
  periodMeta,
  recentDocs,
  spanLabel,
} from "@/lib/domain-types";

const PATENT_PILOT_NOTE = "지식재산 뉴스·EPO 공보 파일럿 기준(공보 수집은 EPO OPS 키 등록 후)";

/** What the counts stand on: the patent sources (always shown on 특허), or the API's own note. */
function CoverageNote({ view }: { view: DomainView }) {
  if (view.kind === "patent") {
    const coverage = view.coverage;
    return (
      <p role="note" aria-label="데이터 범위" className="rounded-xl border bg-muted/40 px-3.5 py-2 text-xs leading-relaxed text-ink-2">
        <span className="font-semibold text-foreground">데이터 범위</span> {coverage?.note || PATENT_PILOT_NOTE}
        {coverage ? (
          <span className="text-muted-foreground">
            {" "}
            · 이번 기간 지식재산 뉴스 {formatNumber(coverage.news)}건, EPO 공보 {formatNumber(coverage.eps)}건, EPO OPS {formatNumber(coverage.ops)}건
          </span>
        ) : null}
        {view.coverage_note ? <span className="block text-muted-foreground">{view.coverage_note}</span> : null}
      </p>
    );
  }
  if (!view.coverage_note) return null;
  return (
    <p role="note" aria-label="데이터 범위" className="rounded-xl border bg-muted/40 px-3.5 py-2 text-xs leading-relaxed text-ink-2">
      <span className="font-semibold text-foreground">데이터 범위</span> {view.coverage_note}
    </p>
  );
}

/** The 연구 or 특허 page body for one API view: header, period, tabs and the open tab. */
export function DomainPage({ view, state }: { view: DomainView; state: DomainState }) {
  const domain = view.kind;
  const meta = DOMAIN_META[domain];
  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <h1 className="text-xl font-semibold">{meta.title}</h1>
          <p className="text-sm text-muted-foreground">
            {meta.intro} {spanLabel(view.window)} 기준(최근 {periodMeta(view.period).unit}, 직전 {spanLabel(view.previous)} 대비)이며 어제까지 집계합니다.
          </p>
        </div>
        <PeriodSelect domain={domain} state={state} />
      </div>
      <CoverageNote view={view} />
      <DomainTabs domain={domain} state={state} />
      {view.overview ? (
        <OverviewBody view={view} tab={view.overview} state={state} />
      ) : view.fields ? (
        <FieldsBody view={view} tab={view.fields} state={state} />
      ) : view.companies ? (
        <CompaniesBody view={view} tab={view.companies} state={state} />
      ) : view.trends ? (
        <TrendsBody view={view} tab={view.trends} state={state} />
      ) : view.documents ? (
        <DocumentsBody view={view} tab={view.documents} state={state} />
      ) : (
        <EmptyNote>이 탭의 데이터를 받지 못했습니다.</EmptyNote>
      )}
    </main>
  );
}

// ── 개요 ──────────────────────────────────────────────────────────────────────────────────

function OverviewBody({ view, tab, state }: { view: DomainView; tab: OverviewTab; state: DomainState }) {
  const domain = view.kind;
  const noun = DOMAIN_META[domain].noun;
  const fieldHref = (field: string) => domainHref(domain, state, { tab: "fields", field, page: 1 });
  return (
    <section aria-label="개요" className="space-y-4">
      <InsightBlock insight={tab.insight} asOf={view.as_of} />
      {tab.kpis.count === 0 ? <EmptyNote className="py-5">이 기간({spanLabel(view.window)})에 집계된 {noun}이 없습니다. 기간을 넓혀 보세요.</EmptyNote> : null}
      <StatStrip stats={kpiStats(view, tab.kpis)} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel id="domain-heatmap" title="기술분야 × 주" question={`최근 ${tab.heatmap.weeks.length}주 동안 분야별 ${noun} 수입니다. 진할수록 많습니다.`} className="lg:col-span-2">
          <HeatmapTable heatmap={tab.heatmap} href={fieldHref} />
        </Panel>
        <Panel id="domain-risers" title="급증 분야 Top 5" question="이번 기간 문헌 수를 이전 4개 기간 평균과 견줍니다." tools={false}>
          <RankBars
            empty="이전 기간보다 늘어난 분야가 없습니다."
            rows={tab.risers.map((r) => ({
              key: r.key,
              label: r.label,
              href: fieldHref(r.key),
              value: r.count,
              display: `${formatNumber(r.count)}건`,
              change: r.ratio ? <span className="font-semibold text-impact-opportunity tabular-nums">×{r.ratio.toFixed(1)}</span> : <span className="font-semibold text-primary">새로</span>,
              sub: `이전 평균 ${r.mean.toFixed(1)}건 · z ${r.z.toFixed(1)}`,
            }))}
          />
        </Panel>
      </div>
    </section>
  );
}

// ── 기업·기관별 ─────────────────────────────────────────────────────────────────────────────

function CompaniesBody({ view, tab, state }: { view: DomainView; tab: CompaniesTab; state: DomainState }) {
  const domain = view.kind;
  const noun = DOMAIN_META[domain].noun;
  const research = domain === "research";
  const entityLabel = research ? ENTITY_LABEL[tab.kind] : "출원 기업";
  const rows: RankRow[] = tab.ranking.map((row, index) => ({
    ...row,
    rank: index + 1,
    href: domainHref(domain, state, row.entity === "org" ? { org: row.key, company: null } : { company: row.key, org: null }),
    selected: row.entity === "org" ? state.org === row.key : state.company === row.key,
  }));
  const watched = tab.watch.companies;
  return (
    <section aria-label="기업·기관별" className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        {research ? (
          <Segments
            label="기관 구분"
            items={(["company", "org"] as const).map((kind) => ({
              key: kind,
              label: ENTITY_LABEL[kind],
              href: domainHref(domain, state, { kind, company: null, org: null }),
              active: tab.kind === kind,
            }))}
          />
        ) : null}
        <ChipRow label="분야 필터" chips={fieldChips(view, (field) => domainHref(domain, state, { field }), state.field)} />
      </div>
      {tab.insight ? <InsightBlock insight={tab.insight} title="기업·기관 인사이트" asOf={view.as_of} /> : null}
      {tab.detail ? <CompanyDetailBlock view={view} tab={tab} state={state} /> : null}
      <Panel id="domain-ranking" title={`${entityLabel} 순위`} question={`이번 기간 ${noun} 수 상위 ${tab.ranking.length}곳입니다. 이름을 누르면 상세를 봅니다.`} tools={false}>
        <CompanyTable rows={rows} label={`${entityLabel} 순위`} emptyText={`이 기간 ${entityLabel}이 확인된 ${noun}이 없습니다.`} />
      </Panel>
      {watched.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel id="domain-watch-mix" title="관심 기업 분야 구성" question={`자사·경쟁사로 지정한 기업 ${tab.watch.total}곳 중 이번 기간 ${noun}이 있는 곳입니다.`}>
            <FieldMixBars rows={watched.map((w) => ({ key: w.company.key, label: w.company.label, fields: w.fields }))} />
          </Panel>
          <Panel id="domain-watch-series" title="관심 기업 추이" question={`최근 ${tab.watch.buckets.length}개 기간(${periodMeta(view.period).unit} 단위)입니다.`}>
            <SeriesChart buckets={tab.watch.buckets} series={watched.slice(0, 8).map((w) => ({ key: w.company.key, label: w.company.label, counts: w.series }))} />
          </Panel>
        </div>
      ) : (
        <EmptyNote>
          이 기간 관심 기업(자사·경쟁사) {noun}이 없습니다. {tab.watch.total ? `지정된 관심 기업 ${tab.watch.total}곳` : "관심 기업은 콘솔의 기업 편집에서 지정합니다"}.
        </EmptyNote>
      )}
    </section>
  );
}

function CompanyDetailBlock({ view, tab, state }: { view: DomainView; tab: CompaniesTab; state: DomainState }) {
  const detail = tab.detail!;
  const domain = view.kind;
  const noun = DOMAIN_META[domain].noun;
  const recent = recentDocs(detail);
  const clear = domainHref(domain, state, { company: null, org: null });
  const fieldHref = (field: string) => domainHref(domain, state, { tab: "fields", field, company: null, org: null });
  return (
    <section aria-labelledby="domain-detail-title" className="space-y-4 rounded-2xl border border-primary/30 bg-primary/[0.03] p-4 md:p-5">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="domain-detail-title" className="text-lg font-bold tracking-tight">
          {detail.label}
        </h2>
        {detail.watched ? <WatchedBadge relation={detail.relation} /> : null}
        {detail.entity === "org" && detail.org_type ? <span className="text-xs text-muted-foreground">{orgTypeLabel(detail.org_type)}</span> : null}
        <span className="text-sm tabular-nums">
          이번 기간 <b>{formatNumber(detail.count)}건</b> · 직전 {formatNumber(detail.previous)}건 <ChangeBadge change={detail.change} count={detail.count} previous={detail.previous} />
        </span>
        <Link href={clear} className="ml-auto text-sm text-muted-foreground hover:text-foreground">
          선택 해제 ✕
        </Link>
      </header>
      {detail.coverage_note ? <p className="text-xs text-muted-foreground">{detail.coverage_note}</p> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel id="domain-detail-fields" title="분야 분포" question="이번 기간 분야별 문헌 수, 직전 기간 대비입니다." tools={false}>
          <RankBars
            empty="이번 기간 분야가 집계된 문헌이 없습니다."
            rows={detail.fields.map((f) => ({
              key: f.key,
              label: f.label,
              href: fieldHref(f.key),
              value: f.count,
              display: `${formatNumber(f.count)}건`,
              change: <ChangeBadge change={f.change} count={f.count} previous={f.previous} />,
            }))}
          />
        </Panel>
        <Panel id="domain-detail-series" title={`${detail.label} 추이`} question={`최근 ${tab.watch.buckets.length}개 기간(${periodMeta(view.period).unit} 단위) ${noun} 수입니다.`}>
          <SeriesChart buckets={tab.watch.buckets} series={[{ key: detail.key, label: detail.label, counts: detail.series }]} height={200} />
        </Panel>
      </div>
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">이번 기간 주목 {noun}</h3>
        <DocList docs={detail.documents} domain={domain} empty={`이 기간 ${detail.label}의 ${noun}이 없습니다.`} />
      </div>
      {recent.length ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">최근 {noun}</h3>
          <DocList docs={recent} domain={domain} empty="" />
        </div>
      ) : null}
    </section>
  );
}

// ── 추이 ──────────────────────────────────────────────────────────────────────────────────

function TrendsBody({ view, tab, state }: { view: DomainView; tab: TrendsTab; state: DomainState }) {
  const domain = view.kind;
  const table = state.view === "table";
  const regionTitle = tab.regions_axis === "country" ? "국가별 추이" : "공개국별 추이";
  const fieldLabel = state.field ? view.field_options.find((o) => o.key === state.field)?.label : undefined;
  const unit = periodMeta(view.period).unit;
  return (
    <section aria-label="추이" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segments
          label="보기 방식"
          items={[
            { key: "chart", label: "차트", href: domainHref(domain, state, { view: "chart" }), active: !table },
            { key: "table", label: "표", href: domainHref(domain, state, { view: "table" }), active: table },
          ]}
        />
        <p className="text-xs text-muted-foreground">
          최근 {tab.buckets.length}개 기간({unit} 단위, {(tab.buckets[0]?.start ?? view.window.start).replaceAll("-", ".")}–{view.window.end.replaceAll("-", ".")}). ▲ 급증·▼ 급감은 마지막 기간이 앞선 {tab.history}개 기간보다 2 표준편차 이상 벗어난 경우입니다.
        </p>
      </div>
      <section aria-label="급증·급감 신호" className="flex flex-wrap gap-1.5">
        {tab.flags.length ? (
          tab.flags.map((f) => (
            <span
              key={`${f.axis}:${f.key}`}
              title={`이번 기간 ${f.current}건, 이전 평균 ${f.mean.toFixed(1)}건, z ${f.z.toFixed(1)}`}
              className={f.flag === "rise" ? "rounded-full bg-impact-opportunity/12 px-2 py-0.5 text-xs font-semibold text-impact-opportunity" : "rounded-full bg-impact-risk/12 px-2 py-0.5 text-xs font-semibold text-impact-risk"}
            >
              {f.flag === "rise" ? "▲ 급증" : "▼ 급감"} {f.label}
              <span className="ml-1 font-normal tabular-nums opacity-80">
                {f.current}건 (평균 {f.mean.toFixed(1)})
              </span>
            </span>
          ))
        ) : (
          <p className="text-xs text-muted-foreground">앞선 기간보다 뚜렷하게 늘거나 준 분야·{tab.regions_axis === "country" ? "국가" : "공개국"}가 없습니다.</p>
        )}
      </section>
      <Panel id="domain-trend-fields" title="기술분야별 추이" question="문헌이 많은 8개 분야와 나머지(기타)입니다.">
        {tab.fields.length ? table ? <SeriesTable caption="기술분야별 기간별 문헌 수" buckets={tab.buckets} series={tab.fields} /> : <SeriesChart buckets={tab.buckets} series={tab.fields} height={300} /> : <EmptyNote>추이를 그릴 문헌이 없습니다.</EmptyNote>}
      </Panel>
      <Panel
        id="domain-trend-regions"
        title={fieldLabel ? `${regionTitle} (${fieldLabel})` : regionTitle}
        question={tab.regions_axis === "country" ? "저자 소속 기관의 국가 기준, 상위 8개국과 나머지입니다." : "특허를 공개한 특허청 기준, 상위 8곳과 나머지입니다."}
        action={state.field ? <Link href={domainHref(domain, state, { field: null })} className="text-xs text-muted-foreground hover:text-foreground">분야 해제 ✕</Link> : undefined}
      >
        {tab.regions.length ? table ? <SeriesTable caption={`${regionTitle} 기간별 문헌 수`} buckets={tab.buckets} series={tab.regions} /> : <SeriesChart buckets={tab.buckets} series={tab.regions} height={300} /> : <EmptyNote>{tab.regions_axis === "country" ? "국가가 확인된 논문이 아직 없습니다." : "공개국이 확인된 특허가 아직 없습니다."}</EmptyNote>}
      </Panel>
    </section>
  );
}

// ── 주목 문헌 ─────────────────────────────────────────────────────────────────────────────

function DocumentsBody({ view, tab, state }: { view: DomainView; tab: DocumentsTab; state: DomainState }) {
  const domain = view.kind;
  const noun = DOMAIN_META[domain].noun;
  const pages = Math.max(1, Math.ceil(tab.total / Math.max(tab.size, 1)));
  const from = tab.total ? (tab.page - 1) * tab.size + 1 : 0;
  const to = Math.min(tab.total, tab.page * tab.size);
  const filter = state.company ?? state.org;
  const filterLabel = state.company ? (tab.items.flatMap((d) => d.companies).find((c) => c.key === state.company)?.label ?? state.company) : state.org;
  return (
    <section aria-label="주목 문헌" className="space-y-4">
      <ChipRow label="분야 필터" chips={fieldChips(view, (field) => domainHref(domain, state, { field, page: 1 }), state.field)} />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">
          {domain === "research" ? "화제 점수(뉴스·커뮤니티 언급, HF 추천, 인용) 순" : "보도 수, 관심 기업 순"} · {formatNumber(tab.total)}건
          {tab.total ? ` 중 ${from}–${to}` : ""}
        </span>
        {filter ? (
          <Link href={domainHref(domain, state, { company: null, org: null, page: 1 })} className="rounded-full border border-primary bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/15">
            {filterLabel} ✕
          </Link>
        ) : null}
      </div>
      <DocList
        docs={tab.items}
        domain={domain}
        empty={tab.total && tab.page > pages ? "이 페이지에는 문헌이 없습니다." : `이 기간 조건에 맞는 ${noun}이 없습니다.`}
        companyHref={(key) => domainHref(domain, state, { company: key, org: null, page: 1 })}
      />
      <Pager page={tab.page} pages={pages} href={(page) => domainHref(domain, state, { page })} />
    </section>
  );
}
