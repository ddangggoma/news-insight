import Link from "next/link";

import { OutcomeBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { FilterBar } from "@/components/console/filter-bar";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { api } from "@/lib/api";
import { formatDateTime, OUTCOME_LABEL } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import type { Outcome, Page, RunOut } from "@/lib/types";

export const metadata = { title: "수집 현황" };

const columns: Column<RunOut>[] = [
  { key: "time", header: "시작", className: "w-28 text-muted-foreground", cell: (run) => formatDateTime(run.started_at) },
  {
    key: "source",
    header: "소스",
    cell: (run) => (
      <Link href={`/console/sources/${run.source_key}`} className="font-mono text-sm hover:underline">
        {run.source_key}
      </Link>
    ),
  },
  { key: "outcome", header: "결과", cell: (run) => <OutcomeBadge outcome={run.outcome} /> },
  { key: "http", header: "HTTP", className: "font-mono", cell: (run) => run.http_status ?? "—" },
  { key: "items", header: "신규/변경/동일", className: "tabular-nums", cell: (run) => `${run.items_new} / ${run.items_updated} / ${run.items_unchanged}` },
  { key: "elapsed", header: "지연", className: "tabular-nums text-muted-foreground", cell: (run) => (run.elapsed_ms ? `${run.elapsed_ms}ms` : "—") },
  { key: "mode", header: "모드", className: "text-muted-foreground", cell: (run) => (run.canary ? "Canary" : "정식") },
  { key: "error", header: "오류", className: "max-w-sm truncate text-destructive", cell: (run) => (run.error_code ? `${run.error_code}` : "") },
];

export default async function RunsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = { outcome: param(sp, "outcome"), source: param(sp, "source") };
  const page = pageParam(sp);
  const data = await api.get<Page<RunOut>>("/api/admin/runs", { ...filters, page });
  const outcomeOptions = (Object.entries(OUTCOME_LABEL) as [Outcome, string][]).map(([value, label]) => ({ value, label }));
  return (
    <>
      <PageHeader title="수집 현황" description="모든 수집 시도의 결과 (최신순)" />
      <FilterBar fields={[{ name: "outcome", label: "결과", value: filters.outcome, options: outcomeOptions }]} />
      <DataTable columns={columns} rows={data.items} rowKey={(run) => run.id} emptyTitle="실행 기록이 없습니다" emptyDescription="V3 이상 소스가 생기면 1분마다 기한이 된 소스를 수집합니다." />
      <PaginationBar pathname="/console/runs" params={filters} page={page} size={data.size} total={data.total} />
    </>
  );
}
