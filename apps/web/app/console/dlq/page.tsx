import Link from "next/link";

import { DeadLetterActions } from "@/components/console/dead-letter-actions";
import { type Column, DataTable } from "@/components/console/data-table";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import type { DeadLetterOut, Page } from "@/lib/types";

export const metadata = { title: "DLQ" };

const STATES = [
  { value: "open", label: "미해결" },
  { value: "resolved", label: "해결됨" },
  { value: "all", label: "전체" },
];

export default async function DeadLettersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const state = (Array.isArray(sp.state) ? sp.state[0] : sp.state) ?? "open";
  const page = pageParam(sp);
  const data = await api.get<Page<DeadLetterOut>>("/api/admin/dead-letters", { state, page });
  const columns: Column<DeadLetterOut>[] = [
    { key: "id", header: "#", className: "w-14 font-mono text-muted-foreground", cell: (row) => row.id },
    { key: "source", header: "소스", cell: (row) => <Link href={`/console/sources/${row.source_key}`} className="font-mono text-sm hover:underline">{row.source_key}</Link> },
    { key: "code", header: "오류", cell: (row) => <Badge variant="destructive">{row.error_code}</Badge> },
    { key: "message", header: "메시지", className: "max-w-md truncate text-muted-foreground", cell: (row) => row.error_message },
    { key: "attempts", header: "시도", className: "tabular-nums", cell: (row) => row.attempts },
    { key: "created", header: "발생", className: "text-muted-foreground", cell: (row) => formatDateTime(row.created_at) },
    {
      key: "actions",
      header: "",
      className: "w-48 text-right",
      cell: (row) => (row.resolved_at ? <span className="text-xs text-muted-foreground">{row.resolution === "retried" ? "재시도함" : "종결"} · {formatDateTime(row.resolved_at)}</span> : <DeadLetterActions id={row.id} />),
    },
  ];
  return (
    <>
      <PageHeader title="DLQ" description="재시도 3회 후에도 실패했거나, 구조 변경·보안 차단으로 격리된 수집" />
      <div className="flex gap-2">
        {STATES.map((option) => (
          <Button key={option.value} asChild size="sm" variant={option.value === state ? "default" : "outline"}>
            <Link href={option.value === "open" ? "/console/dlq" : `/console/dlq?state=${option.value}`}>{option.label}</Link>
          </Button>
        ))}
      </div>
      <DataTable columns={columns} rows={data.items} rowKey={(row) => row.id} emptyTitle="DLQ가 비어 있습니다" />
      <PaginationBar pathname="/console/dlq" params={{ state: param(sp, "state") }} page={page} size={data.size} total={data.total} />
    </>
  );
}
