import { AppLink as Link } from "@/components/app-link";

import { AccessFilters, type AccessFilterValues } from "@/components/console/access-filters";
import { type Column, DataTable } from "@/components/console/data-table";
import { PageHeader } from "@/components/console/page-header";
import { PaginationBar } from "@/components/console/pagination-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  type AccessAccount,
  type AccessKind,
  type AccessRequest,
  type AccountUsage,
  DOCKER_GATEWAY,
  EVENT_LABEL,
  KIND_LABEL,
  LOGIN_OUTCOME_LABEL,
  type LoginEvent,
  type PathUsage,
  type UsageReport,
  describeAgent,
} from "@/lib/access-types";
import { api } from "@/lib/api";
import type { SessionUser } from "@/lib/auth";
import { formatNumber, formatStamp } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import { withQuery } from "@/lib/query";
import { requireAdmin, sessionToken } from "@/lib/session";
import type { Page } from "@/lib/types";

export const metadata = { title: "접속 기록" };

const TABS = [
  { value: "usage", label: "계정별 사용" },
  { value: "requests", label: "요청 내역" },
  { value: "logins", label: "로그인 기록" },
] as const;
type Tab = (typeof TABS)[number]["value"];

const PATH = "/console/access";
const SIZE = 50;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const FAILED = new Set(["login_fail", "login_locked", "locked", "login_pending", "login_rejected", "login_suspended"]);

function href(params: Record<string, string | undefined>): string {
  return withQuery(PATH, params);
}

function AccountCell({ account, tab }: { account: AccessAccount; tab: Tab }) {
  return (
    <Link href={href({ tab, user: String(account.id) })} className="flex min-w-0 flex-col hover:underline">
      <span className="truncate font-medium">{account.name}</span>
      <span className="truncate font-mono text-xs text-muted-foreground">{account.username}</span>
    </Link>
  );
}

function AddressCell({ ip, tab }: { ip: string | null; tab: Tab }) {
  if (!ip) return <span className="text-muted-foreground">—</span>;
  return (
    <Link href={href({ tab, ip })} className="font-mono text-xs hover:underline">
      {ip}
    </Link>
  );
}

function KindBadge({ kind }: { kind: AccessKind }) {
  return <Badge variant={kind === "action" ? "default" : kind === "page" ? "secondary" : "outline"}>{KIND_LABEL[kind]}</Badge>;
}

function usageColumns(): Column<AccountUsage>[] {
  return [
    {
      key: "account",
      header: "계정",
      className: "min-w-40",
      cell: (row) => (
        <span className="flex items-center gap-2">
          <AccountCell account={row.user} tab="requests" />
          {row.user.role === "admin" ? <Badge variant="outline">관리자</Badge> : null}
        </span>
      ),
    },
    { key: "requests", header: "요청", className: "w-20 text-right tabular-nums", cell: (row) => formatNumber(row.requests) },
    { key: "pages", header: "페이지", className: "w-20 text-right tabular-nums", cell: (row) => formatNumber(row.pages) },
    { key: "actions", header: "작업", className: "w-20 text-right tabular-nums", cell: (row) => formatNumber(row.actions) },
    {
      key: "ip",
      header: "최근 접속 주소",
      cell: (row) => (
        <span className="flex items-center gap-1.5">
          <AddressCell ip={row.last_ip} tab="requests" />
          {row.ips > 1 ? <span className="text-xs text-muted-foreground">외 {row.ips - 1}곳</span> : null}
        </span>
      ),
    },
    { key: "last", header: "마지막 활동", className: "w-32 text-muted-foreground tabular-nums", cell: (row) => formatStamp(row.last_at) },
    {
      key: "logins",
      header: "로그인 / 실패",
      className: "w-28 text-right tabular-nums",
      cell: (row) => (
        <Link href={href({ tab: "logins", user: String(row.user.id) })} className="hover:underline">
          {formatNumber(row.logins)} / <span className={row.failures > 0 ? "font-medium text-destructive" : ""}>{formatNumber(row.failures)}</span>
        </Link>
      ),
    },
  ];
}

function pathColumns(filters: AccessFilterValues): Column<PathUsage>[] {
  return [
    {
      key: "path",
      header: "경로",
      cell: (row) => (
        <Link href={href({ tab: "requests", user: filters.user, path: row.path })} className="font-mono text-xs break-all hover:underline">
          {row.path}
        </Link>
      ),
    },
    { key: "kind", header: "종류", className: "w-28", cell: (row) => <KindBadge kind={row.kind} /> },
    { key: "count", header: "횟수", className: "w-20 text-right tabular-nums", cell: (row) => formatNumber(row.count) },
    { key: "last", header: "마지막", className: "w-32 text-muted-foreground tabular-nums", cell: (row) => formatStamp(row.last_at) },
  ];
}

const requestColumns: Column<AccessRequest>[] = [
  { key: "at", header: "시각", className: "w-32 text-muted-foreground tabular-nums", cell: (row) => formatStamp(row.at) },
  { key: "account", header: "계정", className: "w-36", cell: (row) => <AccountCell account={row.user} tab="requests" /> },
  { key: "kind", header: "종류", className: "w-28", cell: (row) => <KindBadge kind={row.kind} /> },
  {
    key: "path",
    header: "경로",
    cell: (row) => (
      <span className="font-mono text-xs break-all">
        {row.method !== "GET" ? <span className="mr-1.5 text-muted-foreground">{row.method}</span> : null}
        {row.path}
        {row.query ? <span className="text-muted-foreground">?{row.query}</span> : null}
      </span>
    ),
  },
  { key: "ip", header: "접속 주소", className: "w-32", cell: (row) => <AddressCell ip={row.ip} tab="requests" /> },
];

const loginColumns: Column<LoginEvent>[] = [
  { key: "at", header: "시각", className: "w-32 text-muted-foreground tabular-nums", cell: (row) => formatStamp(row.at) },
  {
    key: "event",
    header: "내용",
    className: "w-48",
    cell: (row) =>
      FAILED.has(row.event) ? (
        <Badge variant="destructive">{EVENT_LABEL[row.event] ?? row.event}</Badge>
      ) : (
        <Badge variant={row.event === "login_ok" ? "default" : "secondary"}>{EVENT_LABEL[row.event] ?? row.event}</Badge>
      ),
  },
  {
    key: "account",
    header: "계정",
    className: "w-36",
    cell: (row) => (row.user ? <AccountCell account={row.user} tab="logins" /> : <span className="text-xs text-muted-foreground">없는 아이디</span>),
  },
  { key: "ip", header: "접속 주소", className: "w-32", cell: (row) => <AddressCell ip={row.ip} tab="logins" /> },
  {
    key: "agent",
    header: "브라우저",
    className: "max-w-xs truncate text-xs text-muted-foreground",
    cell: (row) => <span title={row.user_agent ?? undefined}>{describeAgent(row.user_agent)}</span>,
  },
];

export default async function AccessPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireAdmin();
  const sp = await searchParams;
  const tab: Tab = TABS.find((option) => option.value === param(sp, "tab"))?.value ?? "usage";
  const day = (name: string) => {
    const value = param(sp, name);
    return value && DAY.test(value) ? value : undefined;
  };
  const user = param(sp, "user");
  const kind = param(sp, "kind");
  const outcome = param(sp, "outcome");
  const filters: AccessFilterValues = {
    user: user && /^\d+$/.test(user) ? user : undefined,
    ip: param(sp, "ip")?.trim().slice(0, 45) || undefined,
    since: day("since"),
    until: day("until"),
    ...(tab === "requests"
      ? { kind: kind && kind in KIND_LABEL ? kind : undefined, path: param(sp, "path")?.trim().slice(0, 300) || undefined }
      : {}),
    ...(tab === "logins" ? { outcome: outcome && outcome in LOGIN_OUTCOME_LABEL ? outcome : undefined } : {}),
  };
  const page = pageParam(sp);
  const headers = { "X-Session-Token": await sessionToken() };
  const query = { ...filters, page, size: SIZE };

  const [users, usage, requests, logins] = await Promise.all([
    api.get<{ items: SessionUser[] }>("/api/admin/users", undefined, headers),
    tab === "usage" ? api.get<UsageReport>("/api/admin/access-log/usage", filters, headers) : null,
    tab === "requests" ? api.get<Page<AccessRequest>>("/api/admin/access-log/requests", query, headers) : null,
    tab === "logins" ? api.get<Page<LoginEvent>>("/api/admin/access-log/logins", query, headers) : null,
  ]);
  const accounts = users.items
    .filter((account) => account.status === "active" || account.status === "suspended")
    .map((account) => ({ value: String(account.id), label: `${account.name} (${account.username})` }));
  const shown = [
    ...(usage?.accounts.map((row) => row.last_ip) ?? []),
    ...(requests?.items.map((row) => row.ip) ?? []),
    ...(logins?.items.map((row) => row.ip) ?? []),
  ];
  const params = { tab, ...filters };

  return (
    <>
      <PageHeader
        title="접속 기록"
        description="누가 언제 어디서 로그인했고 어떤 페이지와 기능을 썼는지 봅니다. 요청 내역은 30일, 로그인 기록은 180일 보관합니다."
      />
      <nav aria-label="접속 기록 보기" className="flex flex-wrap gap-2">
        {TABS.map((option) => (
          <Button key={option.value} asChild size="sm" variant={option.value === tab ? "default" : "outline"}>
            <Link
              href={href({ tab: option.value, user: filters.user, ip: filters.ip, since: filters.since, until: filters.until })}
              aria-current={option.value === tab ? "page" : undefined}
            >
              {option.label}
            </Link>
          </Button>
        ))}
      </nav>
      <AccessFilters
        tab={tab}
        values={filters}
        accounts={accounts}
        kinds={tab === "requests" ? (Object.entries(KIND_LABEL) as [AccessKind, string][]).map(([value, label]) => ({ value, label })) : undefined}
        outcomes={tab === "logins" ? Object.entries(LOGIN_OUTCOME_LABEL).map(([value, label]) => ({ value, label })) : undefined}
      />
      {shown.includes(DOCKER_GATEWAY) ? (
        <p className="text-xs text-muted-foreground">
          {DOCKER_GATEWAY}은 Docker Desktop 게이트웨이 주소입니다. 지금 구성에서는 방문자의 실제 주소가 사이트까지 전달되지 않아 모든
          접속이 이 주소로 보입니다.
        </p>
      ) : null}
      {usage ? (
        <>
          <DataTable
            columns={usageColumns()}
            rows={usage.accounts}
            rowKey={(row) => row.user.id}
            emptyTitle="이 조건의 접속 기록이 없습니다"
            emptyDescription="요청 내역은 이 기능을 배포한 뒤부터 쌓입니다."
          />
          <h2 className="text-lg font-semibold">많이 쓴 경로</h2>
          <DataTable columns={pathColumns(filters)} rows={usage.paths} rowKey={(row) => `${row.kind} ${row.path}`} emptyTitle="기록된 경로가 없습니다" />
        </>
      ) : null}
      {requests ? (
        <>
          <DataTable columns={requestColumns} rows={requests.items} rowKey={(row) => row.id} emptyTitle="이 조건의 요청이 없습니다" />
          <PaginationBar pathname={PATH} params={params} page={page} size={requests.size} total={requests.total} />
        </>
      ) : null}
      {logins ? (
        <>
          <DataTable columns={loginColumns} rows={logins.items} rowKey={(row) => row.id} emptyTitle="이 조건의 로그인 기록이 없습니다" />
          <PaginationBar pathname={PATH} params={params} page={page} size={logins.size} total={logins.total} />
        </>
      ) : null}
    </>
  );
}
