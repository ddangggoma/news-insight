import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { TrackBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { api } from "@/lib/api";
import { formatDateTime, formatNumber, TRACK_LABEL } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import type { ItemRow, Page, Track } from "@/lib/types";

export const metadata = { title: "수집 항목" };

const columns: Column<ItemRow>[] = [
  {
    key: "title",
    header: "제목",
    cell: (item) => (
      <div className="flex min-w-0 flex-col gap-0.5">
        <Link href={`/console/items/${item.id}`} className="line-clamp-2 font-medium hover:underline">
          {item.title}
        </Link>
        <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline">
          {item.source_name} <ExternalLink className="size-3" />
        </a>
      </div>
    ),
  },
  { key: "track", header: "트랙", className: "w-28", cell: (item) => <TrackBadge track={item.track} /> },
  {
    key: "metrics",
    header: "지표",
    className: "w-40 text-xs text-muted-foreground",
    cell: (item) => Object.entries(item.metrics).map(([name, value]) => `${name} ${formatNumber(value)}`).join(" · ") || "—",
  },
  { key: "published", header: "발행", className: "w-28 text-muted-foreground", cell: (item) => formatDateTime(item.published_at) },
  { key: "seen", header: "수집", className: "w-28 text-muted-foreground", cell: (item) => formatDateTime(item.first_seen_at) },
];

export default async function ItemsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = { track: param(sp, "track"), days: param(sp, "days"), q: param(sp, "q"), source: param(sp, "source") };
  const page = pageParam(sp);
  const data = await api.get<Page<ItemRow>>("/api/admin/items", { ...filters, page });
  return (
    <>
      <PageHeader title="수집 항목" description="Seen Ledger에 저장된 항목 (변경이 있을 때만 리비전 추가)" />
      <FilterBar
        fields={[
          { name: "track", label: "트랙", value: filters.track, options: (Object.entries(TRACK_LABEL) as [Track, string][]).map(([value, label]) => ({ value, label })) },
          { name: "days", label: "기간", value: filters.days, options: [{ value: "1", label: "최근 1일" }, { value: "7", label: "최근 7일" }, { value: "30", label: "최근 30일" }] },
        ]}
        query={filters.q}
        searchPlaceholder="제목 검색"
      />
      <DataTable columns={columns} rows={data.items} rowKey={(item) => item.id} emptyTitle="항목이 없습니다" />
      <PaginationBar pathname="/console/items" params={filters} page={page} size={data.size} total={data.total} />
    </>
  );
}
