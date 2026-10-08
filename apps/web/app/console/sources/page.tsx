import Link from "next/link";

import { StageBadge, StatusBadge, TrackBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { FilterBar } from "@/components/console/filter-bar";
import { BulkBar, BulkCheckbox, BulkSelection } from "@/components/console/source-bulk";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { api } from "@/lib/api";
import { formatNumber, formatRelative, REGION_LABEL, STAGE_LABEL, STATUS_LABEL, TRACK_LABEL } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import type { Page, SourceRow } from "@/lib/types";

export const metadata = { title: "소스" };

const columns: Column<SourceRow>[] = [
  { key: "select", header: "", className: "w-8", cell: (row) => <BulkCheckbox sourceKey={row.key} /> },
  {
    key: "name",
    header: "소스",
    cell: (row) => (
      <Link href={`/console/sources/${row.key}`} className="group flex flex-col">
        <span className="font-medium group-hover:underline">{row.name}</span>
        <span className="font-mono text-xs text-muted-foreground">{row.key}</span>
      </Link>
    ),
  },
  { key: "track", header: "트랙", cell: (row) => <TrackBadge track={row.track} /> },
  { key: "region", header: "지역", className: "text-muted-foreground", cell: (row) => REGION_LABEL[row.region] },
  { key: "stage", header: "단계", cell: (row) => <StageBadge stage={row.validation_stage} /> },
  { key: "status", header: "상태", cell: (row) => <StatusBadge status={row.status} /> },
  { key: "next", header: "다음 수집", className: "text-muted-foreground", cell: (row) => formatRelative(row.next_due_at) },
  { key: "items", header: "항목", className: "text-right tabular-nums", cell: (row) => formatNumber(row.items_total) },
  {
    key: "failures",
    header: "연속 실패",
    className: "text-right tabular-nums",
    cell: (row) => (row.consecutive_failures ? <span className="text-destructive">{row.consecutive_failures}</span> : "0"),
  },
];

const options = <T extends string>(labels: Record<T, string>) =>
  (Object.entries(labels) as [T, string][]).map(([value, label]) => ({ value, label }));

export default async function SourcesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = {
    track: param(sp, "track"),
    region: param(sp, "region"),
    stage: param(sp, "stage"),
    status: param(sp, "status"),
    q: param(sp, "q"),
  };
  const page = pageParam(sp);
  const data = await api.get<Page<SourceRow>>("/api/admin/sources", { ...filters, page });
  return (
    <>
      <PageHeader title="소스" description="4개 트랙의 수집 소스와 V0~V6 검증 단계" />
      <FilterBar
        fields={[
          { name: "track", label: "트랙", value: filters.track, options: options(TRACK_LABEL) },
          { name: "region", label: "지역", value: filters.region, options: options(REGION_LABEL) },
          { name: "stage", label: "단계", value: filters.stage, options: options(STAGE_LABEL) },
          { name: "status", label: "상태", value: filters.status, options: options(STATUS_LABEL) },
        ]}
        query={filters.q}
        searchPlaceholder="키 또는 이름 검색"
      />
      <BulkSelection>
        <BulkBar pageKeys={data.items.map((row) => row.key)} />
        <DataTable columns={columns} rows={data.items} rowKey={(row) => row.key} emptyTitle="조건에 맞는 소스가 없습니다" />
      </BulkSelection>
      <PaginationBar pathname="/console/sources" params={filters} page={page} size={data.size} total={data.total} />
    </>
  );
}
