import { type Column, DataTable } from "@/components/console/data-table";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { TrackBadge } from "@/components/console/badges";
import { api } from "@/lib/api";
import { formatNumber, TRACK_LABEL } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import type { MoverOut, Track } from "@/lib/types";

export const metadata = { title: "지표 상승" };

const METRICS = [
  { value: "stars", label: "GitHub 스타" },
  { value: "points", label: "HN 점수" },
  { value: "likes", label: "Bluesky 좋아요" },
  { value: "reactions", label: "DEV 반응" },
  { value: "score", label: "Stack Exchange 점수" },
  { value: "citations", label: "인용 수" },
];

const columns: Column<MoverOut>[] = [
  { key: "title", header: "항목", cell: (row) => <a href={row.item.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">{row.item.title}</a> },
  { key: "source", header: "소스", className: "text-muted-foreground", cell: (row) => row.item.source_name },
  { key: "track", header: "트랙", cell: (row) => <TrackBadge track={row.item.track} /> },
  { key: "baseline", header: "기준", className: "text-right tabular-nums text-muted-foreground", cell: (row) => formatNumber(row.baseline) },
  { key: "current", header: "현재", className: "text-right tabular-nums", cell: (row) => formatNumber(row.current) },
  { key: "delta", header: "증가", className: "text-right font-medium tabular-nums text-emerald-600 dark:text-emerald-400", cell: (row) => `+${formatNumber(row.delta)}` },
];

export default async function TrendsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const metric = param(sp, "metric") ?? "stars";
  const days = param(sp, "days") ?? "1";
  const track = param(sp, "track");
  const movers = await api.get<MoverOut[]>("/api/admin/trends/movers", { metric, days, track, limit: 50 });
  return (
    <>
      <PageHeader title="지표 상승" description="반응 지표 스냅샷으로 계산한 기간 내 증가 상위 항목" />
      <FilterBar
        fields={[
          { name: "metric", label: "지표", value: metric, options: METRICS },
          { name: "days", label: "기간", value: days, options: [{ value: "1", label: "1일" }, { value: "7", label: "7일" }, { value: "30", label: "30일" }] },
          { name: "track", label: "트랙", value: track, options: (Object.entries(TRACK_LABEL) as [Track, string][]).map(([value, label]) => ({ value, label })) },
        ]}
      />
      <DataTable columns={columns} rows={movers} rowKey={(row) => row.item.id} emptyTitle="아직 상승 데이터가 없습니다" emptyDescription="같은 항목의 지표 스냅샷이 2개 이상 쌓여야 계산됩니다." />
    </>
  );
}
