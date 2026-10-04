import { Activity, AlertTriangle, Database, Inbox, Sparkles } from "lucide-react";
import Link from "next/link";

import { TrackBadge } from "@/components/console/badges";
import { HealthBar, StageChart } from "@/components/console/charts";
import { EmptyState } from "@/components/console/empty-state";
import { PageHeader } from "@/components/console/page-header";
import { StatCard } from "@/components/console/stat-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { formatNumber, formatPercent, formatRelative, REGION_LABEL, TRACK_LABEL } from "@/lib/format";
import type { CardStats, DigestOut, ItemRow, MoverOut, Overview, Page } from "@/lib/types";

export const metadata = { title: "대시보드" };

async function latestDigest(): Promise<DigestOut | null> {
  try {
    return await api.get<DigestOut>("/api/admin/digests/latest");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

const MOVER_METRICS = [
  { metric: "stars", label: "스타" },
  { metric: "points", label: "HN 점수" },
  { metric: "likes", label: "좋아요" },
];

export default async function DashboardPage() {
  const [overview, digest, movers, recent, cardStats] = await Promise.all([
    api.get<Overview>("/api/admin/overview"),
    latestDigest(),
    Promise.all(
      MOVER_METRICS.map(({ metric }) =>
        api.get<MoverOut[]>("/api/admin/trends/movers", { metric, days: 1, limit: 5 }),
      ),
    ),
    api.get<Page<ItemRow>>("/api/admin/items", { size: 8 }),
    api.get<CardStats>("/api/admin/cards/stats"),
  ]);
  const topMovers = movers
    .flatMap((rows, index) => rows.map((mover) => ({ ...mover, label: MOVER_METRICS[index].label })))
    .filter((mover) => mover.delta > 0)
    .sort((a, b) => b.delta - a.delta)
    .slice(0, 6);
  const totalSources = overview.tracks.reduce((sum, track) => sum + track.total, 0);
  const activeSources = overview.tracks.reduce((sum, track) => sum + track.active, 0);
  const { health } = overview;
  const successRate = health.runs ? (health.success + health.not_modified) / health.runs : Number.NaN;

  return (
    <>
      <PageHeader title="대시보드" description="수집 포트폴리오, 최근 24시간 수집 건강도, 오늘의 다이제스트" />

      <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-transparent">
        <CardHeader>
          <CardDescription className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" /> 오늘의 다이제스트
          </CardDescription>
          <CardTitle className="text-xl leading-snug text-balance">
            {digest ? digest.content.headline : "아직 발행된 다이제스트가 없습니다"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
            {digest ? digest.content.overview : "매일 05:00 KST에 전일 수집 항목으로 Claude가 요약과 인사이트를 발행합니다."}
          </p>
          {digest ? (
            <Button asChild size="sm">
              <Link href="/console/briefing">브리핑 전체 보기</Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard title="활성 소스" value={`${formatNumber(activeSources)} / ${formatNumber(totalSources)}`} hint="V6 활성 / 등록 후보" icon={Database} />
        <StatCard title="24시간 수집" value={formatNumber(health.runs)} hint={`정상 비율 ${formatPercent(successRate)}`} icon={Activity} />
        <StatCard
          title="신규 항목"
          value={formatNumber(health.items_new)}
          hint={`최근 24시간 · 오늘 카드 ${formatNumber(cardStats.ready_today)}건 · 대기 ${formatNumber(cardStats.pending)}`}
          icon={Sparkles}
        />
        <StatCard title="조치 필요" value={`${health.open_dead_letters} · ${health.paused_sources}`} hint="미해결 DLQ · 일시정지 소스" icon={health.open_dead_letters ? AlertTriangle : Inbox} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">검증 단계 분포</CardTitle>
            <CardDescription>V3부터 Canary 수집, V6부터 발행 대상</CardDescription>
          </CardHeader>
          <CardContent>
            <StageChart stages={overview.stages} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">수집 건강도</CardTitle>
            <CardDescription>최근 {health.window_hours}시간 실행 결과</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <HealthBar health={health} />
            <div className="space-y-3">
              {overview.tracks.map((track) => (
                <div key={track.track} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span>{TRACK_LABEL[track.track]}</span>
                    <span className="text-muted-foreground tabular-nums">
                      활성 {track.active} / 목표 {track.target}
                      <span className="ml-1.5 text-xs">(후보 {track.total})</span>
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-primary" style={{ width: `${Math.min(100, (track.active / track.target) * 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="space-y-1.5">
              <CardTitle className="text-base">최근 수집 항목</CardTitle>
              <CardDescription>방금 들어온 항목</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/console/cards">카드로 보기</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {recent.items.length === 0 ? (
              <EmptyState title="수집된 항목이 없습니다" description="V3 이상 소스가 생기면 자동 수집이 시작됩니다." />
            ) : (
              <ul className="divide-y">
                {recent.items.map((item) => (
                  <li key={item.id} className="flex items-center gap-3 py-2.5">
                    <TrackBadge track={item.track} />
                    <Link href={`/console/items/${item.id}`} className="min-w-0 flex-1 truncate text-sm hover:underline">
                      {item.title_ko ?? item.title}
                    </Link>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatRelative(item.first_seen_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">지표 상승 상위</CardTitle>
              <CardDescription>최근 24시간 반응 지표 증가</CardDescription>
            </CardHeader>
            <CardContent>
              {topMovers.length === 0 ? (
                <EmptyState title="아직 데이터가 없습니다" description="지표 스냅샷이 2개 이상 쌓이면 표시됩니다." />
              ) : (
                <ol className="space-y-3">
                  {topMovers.map((mover, index) => (
                    <li key={`${mover.label}-${mover.item.id}`} className="flex items-center gap-3 text-sm">
                      <span className="w-4 text-muted-foreground tabular-nums">{index + 1}</span>
                      <a href={mover.item.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:underline">
                        {mover.item.title}
                      </a>
                      <span className="shrink-0 text-right">
                        <span className="block font-medium text-emerald-600 tabular-nums dark:text-emerald-400">+{formatNumber(mover.delta)}</span>
                        <span className="block text-[11px] text-muted-foreground">{mover.label}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">지역 분포</CardTitle>
              <CardDescription>발행 시 지역 균형 기준(D13)의 용량 대비</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {overview.regions.map((region) => (
                <div key={region.region} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span>{REGION_LABEL[region.region]}</span>
                    <span className="text-muted-foreground tabular-nums">
                      후보 {region.total} · 용량 {region.capacity}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-chart-3" style={{ width: `${Math.min(100, (region.total / region.capacity) * 100)}%` }} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
