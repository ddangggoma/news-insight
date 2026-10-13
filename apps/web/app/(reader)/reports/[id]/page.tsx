import { ExternalLink, Download } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { archiveReport, retryReport } from "@/app/(reader)/reports/actions";
import { AppLink as Link } from "@/components/app-link";
import { ReportRefresh } from "@/components/reader/report-refresh";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { reportApi } from "@/lib/dossier-api";
import { formatDateTime } from "@/lib/format";
import { type ReportDetail, STATUS_LABEL, isWaiting, waitingText } from "@/lib/report-types";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "동향 보고서", robots: { index: false } };

const FORMATS = [
  { format: "html", label: "HTML" },
  { format: "md", label: "Markdown" },
  { format: "docx", label: "Word" },
  { format: "pptx", label: "PowerPoint" },
] as const;

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  await requireUser();
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id < 1) notFound();
  const report = await reportApi<ReportDetail>("GET", `/${id}`).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });
  const waiting = isWaiting(report.status);

  return (
    <main className="mx-auto max-w-6xl space-y-4 px-4 py-6 md:px-6">
      {waiting ? <ReportRefresh /> : null}
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">
            <Link href="/reports" className="hover:underline">
              동향 보고서
            </Link>
          </p>
          <h1 className="text-xl font-semibold">{report.title ?? report.topic}</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            {STATUS_LABEL[report.status]} · 주제 「{report.topic}」 · 근거 {report.days}일 · {formatDateTime(report.requested_at)} 요청
            {report.requested_by ? ` · ${report.requested_by}` : ""}
            {report.finished_at && report.status === "ready" ? ` · ${formatDateTime(report.finished_at)} 완료` : ""}
            {report.status === "ready" ? ` · 이슈 ${report.stories}건 중 근거 ${report.evidence}건` : ""}
          </p>
          {report.brief ? <p className="mt-1 line-clamp-3 text-sm whitespace-pre-line text-muted-foreground">{report.brief}</p> : null}
        </div>
        {report.status === "ready" ? (
          <Button asChild variant="outline" size="sm">
            <a href={`/reports/${id}/view`} target="_blank" rel="noopener">
              <ExternalLink className="size-4" aria-hidden />새 창으로
            </a>
          </Button>
        ) : null}
        {report.can_archive ? (
          <form action={archiveReport.bind(null, id)}>
            <Button type="submit" variant="ghost" size="sm">
              보관
            </Button>
          </form>
        ) : null}
      </div>

      {report.status === "ready" ? (
        <>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground" aria-label="내보내기">
            <Download className="size-3.5" aria-hidden />
            내보내기
            {FORMATS.map((f) => (
              <a key={f.format} href={`/export/report/${id}?format=${f.format}`} download className="rounded border px-1.5 py-0.5 hover:bg-muted hover:text-foreground">
                {f.label}
              </a>
            ))}
          </p>
          <iframe
            title={`동향 보고서: ${report.title ?? report.topic}`}
            src={`/reports/${id}/view`}
            sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
            className="h-[calc(100vh-14rem)] min-h-[600px] w-full rounded-md border bg-background"
          />
        </>
      ) : null}

      {waiting ? (
        <div className="rounded-md border p-6 text-center" role="status">
          <p className="font-semibold">{STATUS_LABEL[report.status]}</p>
          <p className="mt-1 text-sm text-muted-foreground">{waitingText(report)}</p>
          <p className="mt-2 text-xs text-muted-foreground">이 화면은 자동으로 새로 고쳐집니다. 창을 닫아도 작성은 계속됩니다.</p>
        </div>
      ) : null}

      {report.status === "failed" ? (
        <div className="space-y-3 rounded-md border border-destructive/50 p-6" role="alert">
          <p className="font-semibold text-destructive">보고서를 쓰지 못했습니다</p>
          {report.error ? <p className="text-sm">{report.error}</p> : null}
          <div className="flex flex-wrap gap-2">
            {report.can_retry ? (
              <form action={retryReport.bind(null, id)}>
                <Button type="submit" size="sm">
                  다시 시도
                </Button>
              </form>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link href={`/reports?topic=${encodeURIComponent(report.topic)}`}>주제를 고쳐 다시 요청</Link>
            </Button>
          </div>
        </div>
      ) : null}
    </main>
  );
}
