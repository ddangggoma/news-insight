import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from "lucide-react";

import { EmptyState } from "@/components/console/empty-state";
import { PageHeader } from "@/components/console/page-header";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AlertOut } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata = { title: "운영 알림" };

const SEVERITY = {
  critical: { label: "긴급", icon: OctagonAlert, className: "text-destructive" },
  warning: { label: "주의", icon: AlertTriangle, className: "text-amber-600 dark:text-amber-400" },
  info: { label: "참고", icon: Info, className: "text-muted-foreground" },
} as const;

function AlertRow({ alert }: { alert: AlertOut }) {
  const severity = SEVERITY[alert.severity];
  const Icon = alert.resolved_at ? CheckCircle2 : severity.icon;
  return (
    <li className={cn("flex gap-3 p-4", alert.resolved_at && "opacity-60")}>
      <Icon className={cn("mt-0.5 size-5 shrink-0", alert.resolved_at ? "text-emerald-600" : severity.className)} aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{alert.title}</span>
          <Badge variant={alert.severity === "critical" && !alert.resolved_at ? "destructive" : "outline"}>{severity.label}</Badge>
          <span className="font-mono text-xs text-muted-foreground">{alert.key}</span>
        </div>
        {alert.detail ? <p className="text-sm text-muted-foreground">{alert.detail}</p> : null}
        <p className="text-xs text-muted-foreground">
          발생 {formatDateTime(alert.opened_at)} · 마지막 확인 {formatDateTime(alert.last_seen_at)}
          {alert.resolved_at ? ` · 해소 ${formatDateTime(alert.resolved_at)}` : ""}
          {alert.notified_at ? " · 메일 발송" : ""}
        </p>
      </div>
    </li>
  );
}

export default async function AlertsPage() {
  const alerts = await api.get<AlertOut[]>("/api/admin/alerts", { limit: 100 });
  const open = alerts.filter((alert) => !alert.resolved_at);
  const resolved = alerts.filter((alert) => alert.resolved_at);
  return (
    <>
      <PageHeader
        title="운영 알림"
        description="5분마다 발행 SLA(04:55 동결·05:20 발행), 수집 성공률, DLQ, 작업 큐, 카드 생성을 검사합니다. 새 긴급·주의 알림은 SMTP가 설정되어 있으면 관리자 메일로 갑니다."
      />
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">진행 중 {open.length}건</h2>
        {open.length ? (
          <ul className="divide-y rounded-lg border">{open.map((alert) => <AlertRow key={alert.id} alert={alert} />)}</ul>
        ) : (
          <EmptyState title="진행 중인 알림이 없습니다" description="모든 검사가 통과했습니다." />
        )}
      </section>
      {resolved.length ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-muted-foreground">최근 해소</h2>
          <ul className="divide-y rounded-lg border">{resolved.map((alert) => <AlertRow key={alert.id} alert={alert} />)}</ul>
        </section>
      ) : null}
    </>
  );
}
