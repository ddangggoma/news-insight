import Link from "next/link";

import { DigestStatusBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { api } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { pageParam, type SearchParams } from "@/lib/params";
import type { DigestSummary, Page } from "@/lib/types";

export const metadata = { title: "데일리 다이제스트" };

const columns: Column<DigestSummary>[] = [
  { key: "date", header: "발행일", className: "w-32 font-mono", cell: (row) => row.digest_date },
  {
    key: "headline",
    header: "헤드라인",
    cell: (row) => (
      <Link href={`/console/digests/${row.digest_date}`} className="font-medium hover:underline">
        {row.headline}
      </Link>
    ),
  },
  { key: "status", header: "상태", className: "w-36", cell: (row) => <DigestStatusBadge status={row.status} /> },
  { key: "items", header: "항목", className: "w-20 text-right tabular-nums", cell: (row) => formatNumber(row.item_count) },
  { key: "generated", header: "생성", className: "w-28 text-muted-foreground", cell: (row) => formatDateTime(row.generated_at) },
];

export default async function DigestsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const page = pageParam(await searchParams);
  const data = await api.get<Page<DigestSummary>>("/api/admin/digests", { page });
  return (
    <>
      <PageHeader title="데일리 다이제스트" description="매일 05:00 KST, 전일 수집 항목을 Claude가 트랙·범주·종합 인사이트로 요약" />
      <DataTable columns={columns} rows={data.items} rowKey={(row) => `${row.digest_date}-${row.version}`} emptyTitle="아직 발행된 다이제스트가 없습니다" emptyDescription="launchd 스케줄을 등록하면 매일 05:00에 발행됩니다." />
      <PaginationBar pathname="/console/digests" params={{}} page={page} size={data.size} total={data.total} />
    </>
  );
}
