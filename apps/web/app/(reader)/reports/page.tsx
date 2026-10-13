import type { Metadata } from "next";

import { AppLink as Link } from "@/components/app-link";
import { ReportForm, type ReportDraft } from "@/components/reader/report-form";
import { ReportRefresh } from "@/components/reader/report-refresh";
import { ApiError } from "@/lib/api";
import { dossierApi, reportApi } from "@/lib/dossier-api";
import type { DossierDetail } from "@/lib/dossier-types";
import { formatDateTime } from "@/lib/format";
import { type ReportSummary, STATUS_LABEL, isWaiting } from "@/lib/report-types";
import { requireUser } from "@/lib/session";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "동향 보고서", robots: { index: false } };

type SearchParams = Record<string, string | string[] | undefined>;

const one = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

async function draftFrom(params: SearchParams): Promise<ReportDraft> {
  const draft: ReportDraft = { topic: one(params.topic)?.slice(0, 200) };
  const dossierId = Number(one(params.dossier) ?? 0);
  if (Number.isInteger(dossierId) && dossierId > 0) {
    try {
      const dossier = await dossierApi<DossierDetail>("GET", `/${dossierId}`);
      return { ...draft, topic: draft.topic ?? dossier.title, brief: dossier.description ?? undefined, dossierId, dossierTitle: dossier.title };
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }
  return draft;
}

const BADGE: Record<string, string> = {
  queued: "border-muted-foreground/40 text-muted-foreground",
  running: "border-primary text-primary",
  ready: "border-emerald-600 text-emerald-700 dark:text-emerald-400",
  failed: "border-destructive text-destructive",
};

export default async function ReportsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const [reports, draft] = await Promise.all([reportApi<ReportSummary[]>("GET", ""), draftFrom(await searchParams)]);
  return (
    <main className="mx-auto max-w-4xl space-y-5 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-xl font-semibold">동향 보고서</h1>
        <p className="text-sm text-muted-foreground">
          주제나 정보를 주면 수집된 기사·논문·커뮤니티 카드를 근거로 동향 보고서를 씁니다. 사건을 시간(주체의 과거와 다음 행보)과 공간(같은 대상을 둔 다른 주체들)으로 넓혀 봅니다.
        </p>
      </div>
      <ReportForm draft={draft} />
      {reports.some((r) => isWaiting(r.status)) ? <ReportRefresh seconds={20} /> : null}
      <section aria-label="보고서 목록" className="space-y-2">
        <h2 className="text-sm font-semibold">팀의 보고서</h2>
        {reports.length ? (
          <ul className="divide-y rounded-md border">
            {reports.map((r) => (
              <li key={r.id}>
                <Link href={`/reports/${r.id}`} className="block space-y-1 p-4 hover:bg-muted/50">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn("rounded-full border px-2 py-0.5 text-xs", BADGE[r.status])}>
                      {STATUS_LABEL[r.status]}
                      {r.status === "queued" && r.position ? ` · ${r.position}번째` : ""}
                    </span>
                    <span className="font-semibold">{r.title ?? r.topic}</span>
                  </div>
                  {r.bottom_line ? <p className="line-clamp-2 text-sm text-muted-foreground">{r.bottom_line}</p> : null}
                  {r.status === "failed" && r.error ? <p className="line-clamp-1 text-sm text-destructive">{r.error}</p> : null}
                  <p className="text-xs text-muted-foreground">
                    {r.title ? `주제: ${r.topic} · ` : ""}
                    {formatDateTime(r.requested_at)} 요청{r.requested_by ? ` · ${r.requested_by}` : ""} · 근거 {r.days}일
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-md border py-12 text-center">
            <p className="font-semibold">아직 보고서가 없습니다</p>
            <p className="mt-1 text-sm text-muted-foreground">위에서 주제를 입력해 첫 보고서를 요청하세요.</p>
          </div>
        )}
      </section>
    </main>
  );
}
