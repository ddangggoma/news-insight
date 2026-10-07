import Link from "next/link";

import { type Column, DataTable } from "@/components/console/data-table";
import { PageHeader } from "@/components/console/page-header";
import { UserActions } from "@/components/console/user-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { SessionUser, UserStatus } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { requireAdmin, sessionToken } from "@/lib/session";

export const metadata = { title: "사용자" };

const TABS: { value: UserStatus; label: string; empty: string }[] = [
  { value: "pending", label: "승인 대기", empty: "승인을 기다리는 가입 신청이 없습니다" },
  { value: "active", label: "사용 중", empty: "사용 중인 계정이 없습니다" },
  { value: "suspended", label: "정지", empty: "정지된 계정이 없습니다" },
  { value: "rejected", label: "거절", empty: "거절된 신청이 없습니다 (30일 뒤 자동 삭제)" },
];

export default async function UsersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const me = await requireAdmin();
  const requested = param(await searchParams, "status");
  const tab = TABS.find((t) => t.value === requested) ?? TABS[0];
  const data = await api.get<{ items: SessionUser[]; counts: Record<UserStatus, number> }>(
    "/api/admin/users",
    { status: tab.value },
    { "X-Session-Token": await sessionToken() },
  );
  const columns: Column<SessionUser>[] = [
    {
      key: "username",
      header: "아이디",
      cell: (row) => (
        <Link href={`/console/users/${row.id}`} className="font-mono text-sm hover:underline">
          {row.username}
        </Link>
      ),
    },
    { key: "name", header: "이름", cell: (row) => row.name },
    {
      key: "role",
      header: "권한",
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          <Badge variant={row.role === "admin" ? "default" : "secondary"}>{row.role === "admin" ? "관리자" : "독자"}</Badge>
          {row.locked ? <Badge variant="destructive">잠김</Badge> : null}
        </span>
      ),
    },
    { key: "created", header: "가입 신청", className: "text-muted-foreground", cell: (row) => formatDateTime(row.created_at) },
    { key: "login", header: "마지막 로그인", className: "text-muted-foreground", cell: (row) => formatDateTime(row.last_login_at) },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (row) =>
        row.id === me.id ? <span className="text-xs text-muted-foreground">내 계정</span> : <UserActions user={row} />,
    },
  ];
  return (
    <>
      <PageHeader title="사용자" description="가입 신청을 승인하거나 거절하고, 계정의 권한과 사용 여부를 관리합니다." />
      <nav aria-label="사용자 상태" className="flex flex-wrap gap-2">
        {TABS.map((option) => (
          <Button key={option.value} asChild size="sm" variant={option.value === tab.value ? "default" : "outline"}>
            <Link
              href={option.value === "pending" ? "/console/users" : `/console/users?status=${option.value}`}
              aria-current={option.value === tab.value ? "page" : undefined}
            >
              {option.label} {data.counts[option.value] ?? 0}
            </Link>
          </Button>
        ))}
      </nav>
      <DataTable columns={columns} rows={data.items} rowKey={(row) => row.id} emptyTitle={tab.empty} />
    </>
  );
}
