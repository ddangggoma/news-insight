import Link from "next/link";

import { StageBadge, StatusBadge, TrackBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { api } from "@/lib/api";
import { formatNumber, formatPercent, REGION_LABEL } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import type { SourceQualityRow } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "소스 품질" };

function RelevanceBar({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-muted-foreground">분류 대기</span>;
  const tone = value < 0.15 ? "bg-destructive" : value < 0.35 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full", tone)} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums">{formatPercent(value)}</span>
    </div>
  );
}

const columns: Column<SourceQualityRow>[] = [
  {
    key: "name",
    header: "소스",
    cell: (row) => (
      <Link href={`/console/sources/${row.key}`} className="group flex flex-col">
        <span className="font-medium group-hover:underline">{row.name}</span>
        <span className="text-xs text-muted-foreground">
          {REGION_LABEL[row.region]}
          {row.paused_reason ? ` · ${row.paused_reason}` : ""}
        </span>
      </Link>
    ),
  },
  { key: "track", header: "트랙", cell: (row) => <TrackBadge track={row.track} /> },
  { key: "stage", header: "단계", cell: (row) => <StageBadge stage={row.validation_stage} /> },
  { key: "status", header: "상태", cell: (row) => <StatusBadge status={row.status} /> },
  { key: "items", header: "7일 항목", className: "text-right tabular-nums", cell: (row) => formatNumber(row.items_7d) },
  { key: "classified", header: "분류됨", className: "text-right tabular-nums", cell: (row) => formatNumber(row.classified_7d) },
  { key: "relevance", header: "DX 관련 비율", cell: (row) => <RelevanceBar value={row.relevance} /> },
  {
    key: "translation",
    header: "카드 성공률",
    className: "text-right tabular-nums",
    cell: (row) => (row.translation === null ? "—" : formatPercent(row.translation)),
  },
];

export default async function QualityPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const order = param(sp, "order") ?? "worst";
  const rows = await api.get<SourceQualityRow[]>("/api/admin/sources/quality", { order, limit: 300 });
  return (
    <>
      <PageHeader
        title="소스 품질"
        description="최근 7일 카드로 본 소스별 DX 관련 비율과 카드 성공률입니다. 매일 03:30에 관련 비율 15% 미만(분류 20건 이상)은 일시정지, 35% 이상은 V5 통과 후 트랙 정원 안에서 정식(V6)으로 올립니다."
      />
      <FilterBar
        fields={[
          {
            name: "order",
            label: "정렬",
            value: order,
            options: [
              { value: "worst", label: "관련 비율 낮은 순" },
              { value: "best", label: "관련 비율 높은 순" },
            ],
          },
        ]}
      />
      <DataTable columns={columns} rows={rows} rowKey={(row) => row.key} emptyTitle="최근 7일 수집된 항목이 없습니다" />
    </>
  );
}
