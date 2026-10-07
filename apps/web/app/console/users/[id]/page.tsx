import Link from "next/link";
import { notFound } from "next/navigation";

import { type Column, DataTable } from "@/components/console/data-table";
import { PageHeader } from "@/components/console/page-header";
import { UserActions } from "@/components/console/user-actions";
import { ApiError, api } from "@/lib/api";
import type { SessionUser } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { requireAdmin, sessionToken } from "@/lib/session";

export const metadata = { title: "사용자 기록" };

interface EventOut {
  id: number;
  at: string;
  event: string;
  actor_id: number | null;
  ip: string | null;
  user_agent: string | null;
}

const EVENT_LABEL: Record<string, string> = {
  signup: "가입 신청",
  create_admin: "관리자 계정 생성(CLI)",
  login_ok: "로그인",
  login_fail: "로그인 실패",
  login_locked: "잠긴 계정으로 로그인 시도",
  login_pending: "승인 전 로그인 시도",
  login_rejected: "거절된 계정으로 로그인 시도",
  login_suspended: "정지된 계정으로 로그인 시도",
  locked: "연속 실패로 잠김",
  logout: "로그아웃",
  logout_others: "다른 기기 모두 로그아웃",
  approve: "승인",
  reject: "거절",
  suspend: "정지",
  reactivate: "다시 사용",
  role_admin: "관리자로 변경",
  role_reader: "독자로 변경",
  password_change: "비밀번호 변경",
  password_reset: "비밀번호 초기화",
  unlock: "잠금 해제",
};

const STATUS_LABEL = { pending: "승인 대기", active: "사용 중", rejected: "거절", suspended: "정지" } as const;

export default async function UserPage({ params }: { params: Promise<{ id: string }> }) {
  const me = await requireAdmin();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const headers = { "X-Session-Token": await sessionToken() };
  let user: SessionUser;
  let events: EventOut[];
  try {
    [user, events] = await Promise.all([
      api.get<SessionUser>(`/api/admin/users/${id}`, undefined, headers),
      api.get<EventOut[]>(`/api/admin/users/${id}/events`, undefined, headers),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const columns: Column<EventOut>[] = [
    { key: "at", header: "시각", className: "w-32 text-muted-foreground", cell: (row) => formatDateTime(row.at) },
    { key: "event", header: "내용", cell: (row) => EVENT_LABEL[row.event] ?? row.event },
    { key: "actor", header: "처리", className: "text-muted-foreground", cell: (row) => (row.actor_id ? `관리자 #${row.actor_id}` : "") },
    { key: "ip", header: "접속 주소", className: "font-mono text-xs text-muted-foreground", cell: (row) => row.ip ?? "" },
    { key: "agent", header: "브라우저", className: "max-w-xs truncate text-xs text-muted-foreground", cell: (row) => row.user_agent ?? "" },
  ];
  return (
    <>
      <PageHeader
        title={`${user.name} (${user.username})`}
        description={`${user.role === "admin" ? "관리자" : "독자"} · ${STATUS_LABEL[user.status]}${user.locked ? " · 잠김" : ""} · 가입 신청 ${formatDateTime(user.created_at)}`}
        actions={user.id === me.id ? null : <UserActions user={user} />}
      />
      <Link href="/console/users" className="text-sm text-muted-foreground hover:underline">
        ← 사용자 목록
      </Link>
      <h2 className="text-lg font-semibold">기록 (최근 100건, 180일 보관)</h2>
      <DataTable columns={columns} rows={events} rowKey={(row) => row.id} emptyTitle="기록이 없습니다" />
    </>
  );
}
