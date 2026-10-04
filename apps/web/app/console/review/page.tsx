import { Download, Shuffle } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/console/empty-state";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { ReviewCard } from "@/components/console/review-card";
import { StatCard } from "@/components/console/stat-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { CATEGORY_LABEL, formatNumber, formatPercent, TRACK_LABEL } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { withQuery } from "@/lib/query";
import type { ReviewBucket, ReviewSample, ReviewStats, Track } from "@/lib/types";

export const metadata = { title: "관련성 검토" };

function newSeed(): string {
  return Math.random().toString(36).slice(2, 10);
}

function rate(bucket: ReviewBucket): number {
  const decided = bucket.relevant + bucket.irrelevant;
  return decided ? bucket.relevant / decided : Number.NaN;
}

function BucketTable({ title, rows, label }: { title: string; rows: ReviewBucket[]; label: (key: string) => string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">아직 검토 기록이 없습니다.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {rows.map((row) => (
              <li key={row.key} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate">{label(row.key)}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  관련 {row.relevant} · 무관 {row.irrelevant} · 애매 {row.unsure}
                </span>
                <span className="w-14 text-right font-medium tabular-nums">{formatPercent(rate(row))}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default async function ReviewPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = { track: param(sp, "track"), days: param(sp, "days"), size: param(sp, "size") };
  const seed = param(sp, "seed");
  if (!seed) redirect(withQuery("/console/review", { ...filters, seed: newSeed() }));
  const [sample, stats] = await Promise.all([
    api.get<ReviewSample>("/api/admin/reviews/sample", { ...filters, size: filters.size ?? 30, seed }),
    api.get<ReviewStats>("/api/admin/reviews/stats"),
  ]);
  const overall = stats.overall;
  return (
    <>
      <PageHeader
        title="관련성 검토"
        description="한국어 카드가 만들어진 항목을 무작위로 뽑아 DX 관련성을 표시합니다. 같은 샘플 번호(seed)는 언제 열어도 같은 항목을 보여 줍니다."
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <a href="/console/review/export">
                <Download /> CSV 내보내기
              </a>
            </Button>
            <Button asChild size="sm">
              <Link href={withQuery("/console/review", { ...filters, seed: newSeed() })}>
                <Shuffle /> 새 샘플
              </Link>
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4 [&>*]:min-w-0">
        <StatCard title="이 샘플 진행" value={`${sample.reviewed} / ${sample.items.length}`} hint={`샘플 번호 ${sample.seed}`} />
        <StatCard title="누적 검토" value={formatNumber(overall.total)} hint={`애매 ${formatNumber(overall.unsure)}건 포함`} />
        <StatCard title="관련 비율" value={formatPercent(rate(overall))} hint="관련 / (관련 + 무관)" />
        <StatCard title="무관 판정" value={formatNumber(overall.irrelevant)} hint="P4 관련성 필터의 학습·평가 자료" />
      </div>
      <FilterBar
        fields={[
          {
            name: "track",
            label: "트랙",
            value: filters.track,
            options: (Object.entries(TRACK_LABEL) as [Track, string][]).map(([value, label]) => ({ value, label })),
          },
          {
            name: "days",
            label: "기간",
            value: filters.days,
            options: [
              { value: "1", label: "최근 1일" },
              { value: "7", label: "최근 7일" },
              { value: "30", label: "최근 30일" },
            ],
          },
          {
            name: "size",
            label: "샘플 크기",
            value: filters.size,
            options: [
              { value: "20", label: "20건" },
              { value: "50", label: "50건" },
              { value: "100", label: "100건" },
            ],
          },
        ]}
      />
      {sample.items.length === 0 ? (
        <EmptyState title="검토할 카드가 없습니다" description="한국어 카드가 생성되면 표본을 뽑을 수 있습니다." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 [&>*]:min-w-0">
          {sample.items.map((view, index) => (
            <ReviewCard key={view.item.id} view={view} seed={sample.seed} index={index} />
          ))}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
        <BucketTable title="트랙별 관련 비율" rows={stats.by_track} label={(key) => TRACK_LABEL[key as Track] ?? key} />
        <BucketTable title="범주별 관련 비율" rows={stats.by_category} label={(key) => CATEGORY_LABEL[key] ?? key} />
        <BucketTable title="무관 판정이 많은 소스" rows={stats.worst_sources} label={(key) => key} />
      </div>
    </>
  );
}
