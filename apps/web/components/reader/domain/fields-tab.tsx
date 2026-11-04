import { RankBars } from "@/components/reader/insight-parts";
import { Panel } from "@/components/reader/radar/parts";
import { SeriesChart, ThemeBars } from "@/components/reader/domain/charts";
import { ChangeBadge, type Chip, ChipRow, DocList, EmptyNote, InsightBlock } from "@/components/reader/domain/parts";
import { formatNumber } from "@/lib/format";
import { DOMAIN_META, type DomainState, type DomainView, type FieldsTab, OTHER_FIELD, domainHref, orgTypeLabel, periodMeta } from "@/lib/domain-types";

/** 기술분야별: a chip per field, then the chosen field's themes, line, companies and documents. */
export function FieldsBody({ view, tab, state }: { view: DomainView; tab: FieldsTab; state: DomainState }) {
  const domain = view.kind;
  const noun = DOMAIN_META[domain].noun;
  const detail = tab.detail;
  const chips: Chip[] = tab.items.map((item) => ({
    key: item.key,
    label: item.label,
    href: domainHref(domain, state, { field: item.key }),
    active: tab.selected === item.key,
    count: item.count,
  }));
  if (tab.other.count > 0 || tab.selected === OTHER_FIELD) {
    chips.push({ key: OTHER_FIELD, label: tab.other.label, href: domainHref(domain, state, { field: OTHER_FIELD }), active: tab.selected === OTHER_FIELD, count: tab.other.count });
  }
  const empty = detail.count === 0 && detail.series.every((n) => n === 0);
  const companyHref = (key: string) => domainHref(domain, state, { tab: "companies", field: detail.key, company: key, org: null, kind: "company" });
  const orgHref = (name: string) => domainHref(domain, state, { tab: "companies", field: detail.key, org: name, company: null, kind: "org" });
  return (
    <section aria-label="기술분야별" className="space-y-4">
      <ChipRow label="기술분야" chips={chips} />
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-bold tracking-tight">{detail.label}</h2>
        <span className="text-sm tabular-nums">
          이번 기간 <b>{formatNumber(detail.count)}건</b> · 직전 {formatNumber(detail.previous)}건 <ChangeBadge change={detail.change} count={detail.count} previous={detail.previous} />
        </span>
      </header>
      <InsightBlock insight={detail.insight} title={`${detail.label} 인사이트`} compact />
      {empty ? (
        <EmptyNote>
          최근 {tab.buckets.length}개 기간 동안 {detail.label} 분야 {noun}이 없습니다.
        </EmptyNote>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel id="domain-themes" title="테마별 문헌 수" question="이번 기간과 직전 기간, 많은 순 10개 테마입니다.">
              {detail.themes.some((t) => t.count || t.previous) ? <ThemeBars themes={detail.themes} /> : <EmptyNote>테마가 분류된 문헌이 없습니다.</EmptyNote>}
            </Panel>
            <Panel id="domain-field-series" title={`${detail.label} 추이`} question={`최근 ${tab.buckets.length}개 기간(${periodMeta(view.period).unit} 단위) ${noun} 수입니다.`}>
              <SeriesChart buckets={tab.buckets} series={[{ key: detail.key, label: detail.label, counts: detail.series }]} height={220} />
            </Panel>
          </div>
          <div className={domain === "research" ? "grid gap-4 lg:grid-cols-2" : "grid gap-4"}>
            <Panel id="domain-field-companies" title="주요 기업" question={`이 분야 ${noun}이 많은 등록 기업 Top 10, 직전 기간 대비입니다.`} tools={false}>
              <RankBars
                empty="이 분야에서 기업이 확인된 문헌이 없습니다."
                rows={detail.companies.map((c) => ({
                  key: c.key,
                  label: c.watched ? `${c.label} · 관심` : c.label,
                  href: companyHref(c.key),
                  value: c.count,
                  display: `${formatNumber(c.count)}건`,
                  change: <ChangeBadge change={c.change} count={c.count} previous={c.previous} />,
                }))}
              />
            </Panel>
            {domain === "research" ? (
              <Panel id="domain-field-orgs" title="주요 대학·연구기관" question="기업 레지스트리에 없는 저자 소속 기관 Top 10입니다." tools={false}>
                <RankBars
                  empty="이 분야에서 기관이 확인된 논문이 없습니다."
                  rows={detail.orgs.map((o) => ({
                    key: o.name,
                    label: o.name,
                    href: orgHref(o.name),
                    value: o.count,
                    display: `${formatNumber(o.count)}건`,
                    change: <ChangeBadge change={o.change} count={o.count} previous={o.previous} />,
                    sub: orgTypeLabel(o.org_type) || undefined,
                  }))}
                />
              </Panel>
            ) : null}
          </div>
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">대표 {noun}</h3>
            <DocList docs={detail.documents} domain={domain} empty={`이 기간 ${detail.label} 분야 ${noun}이 없습니다.`} companyHref={companyHref} />
          </div>
        </>
      )}
    </section>
  );
}
