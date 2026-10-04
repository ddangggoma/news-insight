import { Bot, Clock, Cpu, Sparkles, TriangleAlert } from "lucide-react";

import { FilterBar } from "@/components/console/filter-bar";
import { EmptyState } from "@/components/console/empty-state";
import { NewsCard } from "@/components/console/news-card";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { StatCard } from "@/components/console/stat-card";
import { api } from "@/lib/api";
import { CATEGORY_LABEL, formatNumber, formatRelative, REGION_LABEL, TRACK_LABEL } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL, SCOPE_LABEL } from "@/lib/taxonomy";
import type { CardStats, CardView, Page, Region, Track } from "@/lib/types";

export const metadata = { title: "카드 뉴스" };

const ENGINE_LABEL: Record<string, string> = { agy: "Antigravity", qwen: "로컬 Qwen" };

function options<T extends string>(labels: Record<T, string>) {
  return (Object.entries(labels) as [T, string][]).map(([value, label]) => ({ value, label }));
}

export default async function CardsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = {
    track: param(sp, "track"),
    category: param(sp, "category"),
    region: param(sp, "region"),
    days: param(sp, "days"),
    q: param(sp, "q"),
    field: param(sp, "field"),
    business: param(sp, "business"),
    impact: param(sp, "impact"),
    scope: param(sp, "scope"),
    view: param(sp, "view"),
  };
  const page = pageParam(sp);
  const [data, stats] = await Promise.all([
    api.get<Page<CardView>>("/api/admin/cards", {
      ...filters,
      view: undefined,
      dedup: filters.view === "story" ? "true" : undefined,
      page,
    }),
    api.get<CardStats>("/api/admin/cards/stats"),
  ]);
  const quota = stats.last_run?.quota;
  const engines = Object.entries(stats.by_engine)
    .map(([engine, count]) => `${ENGINE_LABEL[engine] ?? engine} ${formatNumber(count)}`)
    .join(" · ");
  return (
    <>
      <PageHeader
        title="카드 뉴스"
        description="수집된 모든 항목을 한국어 카드(제목·요약·키워드·출처)로 정리합니다. Antigravity 우선, 한도 소진 시 로컬 Qwen."
      />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4 [&>*]:min-w-0">
        <StatCard title="오늘 만든 카드" value={formatNumber(stats.ready_today)} hint={`누적 ${formatNumber(stats.ready)}건`} icon={Sparkles} />
        <StatCard title="생성 대기" value={formatNumber(stats.pending)} hint="10분마다 자동 처리" icon={Clock} />
        <StatCard title="엔진별 카드" value={engines || "—"} hint={stats.failed ? `실패 ${formatNumber(stats.failed)}건 (3회 재시도 후)` : "실패 없음"} icon={stats.failed ? TriangleAlert : Cpu} />
        <StatCard
          title="Antigravity 한도"
          value={quota?.weekly != null ? `주간 ${quota.weekly}% · 5시간 ${quota.five_hour ?? "—"}%` : "—"}
          hint={stats.last_run ? `마지막 실행 ${formatRelative(stats.last_run.started_at)}` : "아직 실행 기록 없음"}
          icon={Bot}
        />
      </div>
      <FilterBar
        fields={[
          { name: "track", label: "트랙", value: filters.track, options: options<Track>(TRACK_LABEL) },
          { name: "category", label: "범주", value: filters.category, options: options(CATEGORY_LABEL) },
          { name: "region", label: "지역", value: filters.region, options: options<Region>(REGION_LABEL) },
          { name: "business", label: "사업부", value: filters.business, options: options(BUSINESS_LABEL) },
          { name: "field", label: "분야", value: filters.field, options: options(FIELD_LABEL) },
          { name: "impact", label: "영향", value: filters.impact, options: options(IMPACT_LABEL) },
          {
            name: "scope",
            label: "범위",
            value: filters.scope,
            options: [{ value: "relevant", label: "DX 관련만" }, ...options(SCOPE_LABEL)],
          },
          {
            name: "view",
            label: "보기",
            value: filters.view,
            options: [{ value: "story", label: "이슈별 1건 (중복 묶기)" }],
          },
          {
            name: "days",
            label: "기간",
            value: filters.days,
            options: [
              { value: "1", label: "최근 1일" },
              { value: "3", label: "최근 3일" },
              { value: "7", label: "최근 7일" },
              { value: "30", label: "최근 30일" },
            ],
          },
        ]}
        query={filters.q}
        searchPlaceholder="제목·키워드 검색"
      />
      {data.items.length === 0 ? (
        <EmptyState title="카드가 없습니다" description="수집 항목이 들어오면 10분 안에 한국어 카드가 만들어집니다." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 [&>*]:min-w-0">
          {data.items.map((view) => (
            <NewsCard key={view.item.id} view={view} />
          ))}
        </div>
      )}
      <PaginationBar pathname="/console/cards" params={filters} page={page} size={data.size} total={data.total} />
    </>
  );
}
