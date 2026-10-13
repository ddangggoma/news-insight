/** Trend reports on request (plan 17 R1), as the API returns them. */

export type ReportStatus = "queued" | "running" | "ready" | "failed";

export interface ReportSummary {
  id: number;
  topic: string;
  title: string | null;
  days: number;
  status: ReportStatus;
  requested_by: string | null;
  requested_at: string;
  finished_at: string | null;
  bottom_line: string | null;
  error: string | null;
  mine: boolean;
  position: number | null;
}

export interface ReportDetail extends ReportSummary {
  brief: string | null;
  dossier_id: number | null;
  started_at: string | null;
  model: string | null;
  evidence: number;
  stories: number;
  can_retry: boolean;
  can_archive: boolean;
}

export const REPORT_WINDOWS = [
  { days: 30, label: "최근 30일" },
  { days: 90, label: "최근 90일" },
  { days: 180, label: "최근 180일" },
  { days: 365, label: "최근 1년" },
] as const;

export const STATUS_LABEL: Record<ReportStatus, string> = {
  queued: "대기 중",
  running: "작성 중",
  ready: "완료",
  failed: "실패",
};

/** One line for the waiting state: where the report is in the queue. */
export function waitingText(report: Pick<ReportSummary, "status" | "position">): string {
  if (report.status === "running") return "Claude가 근거를 모아 보고서를 쓰고 있습니다. 보통 5~15분 걸립니다.";
  if (report.status === "queued") {
    return report.position && report.position > 1
      ? `앞에 ${report.position - 1}건이 있습니다. 차례가 되면 작성을 시작합니다.`
      : "곧 작성을 시작합니다(1분 안).";
  }
  return "";
}

export function isWaiting(status: ReportStatus): boolean {
  return status === "queued" || status === "running";
}
