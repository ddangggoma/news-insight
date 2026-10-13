"use client";

import { useActionState } from "react";

import { type RequestState, requestReport } from "@/app/(reader)/reports/actions";
import { Button } from "@/components/ui/button";
import { REPORT_WINDOWS } from "@/lib/report-types";

const field = "w-full rounded-md border bg-background px-3 py-2 text-sm";

export interface ReportDraft {
  topic?: string;
  brief?: string;
  days?: number;
  dossierId?: number;
  dossierTitle?: string;
}

/** Request a trend report: a topic, what the reader already knows, and the evidence window. */
export function ReportForm({ draft = {} }: { draft?: ReportDraft }) {
  const [state, action, pending] = useActionState<RequestState, FormData>(requestReport, {});
  return (
    <form action={action} className="space-y-4 rounded-md border p-4">
      {draft.dossierId ? <input type="hidden" name="dossier_id" value={draft.dossierId} /> : null}
      <div className="space-y-1.5">
        <label htmlFor="r-topic" className="text-sm font-medium">
          주제
        </label>
        <input
          id="r-topic"
          name="topic"
          required
          minLength={2}
          maxLength={200}
          defaultValue={draft.topic}
          className={field}
          placeholder="예: 월드 모델과 JEPA, 얀 르쿤의 AMI Labs 창업 / 온디바이스 AI 칩 경쟁"
        />
      </div>
      <div className="space-y-1.5">
        <label htmlFor="r-brief" className="text-sm font-medium">
          정보·관점 <span className="font-normal text-muted-foreground">(선택: 알고 있는 사실, 궁금한 점, 꼭 다룰 기업·인물)</span>
        </label>
        <textarea
          id="r-brief"
          name="brief"
          rows={4}
          maxLength={4000}
          defaultValue={draft.brief}
          className={field}
          placeholder="예: 르쿤이 Meta를 떠나 JEPA 기반 스타트업을 세웠다. 르쿤의 과거·다음 행보와, 월드 모델을 하는 다른 기업들의 움직임을 알고 싶다."
        />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <label htmlFor="r-days" className="text-sm font-medium">
            근거 기간
          </label>
          <select id="r-days" name="days" defaultValue={String(draft.days ?? 90)} className="h-9 rounded-md border bg-background px-2 text-sm">
            {REPORT_WINDOWS.map((w) => (
              <option key={w.days} value={w.days}>
                {w.label}
              </option>
            ))}
          </select>
        </div>
        {draft.dossierTitle ? <p className="text-xs text-muted-foreground">주제 파일 「{draft.dossierTitle}」의 카드도 함께 씁니다.</p> : null}
        <Button type="submit" disabled={pending} className="ml-auto">
          {pending ? "요청 중…" : "보고서 요청"}
        </Button>
      </div>
      {state.error ? (
        <p role="alert" className="text-sm text-destructive">
          {state.error}
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        서버의 Claude(Opus)가 검색 계획을 세우고, 수집된 카드에서 근거를 모아 주제의 흐름(시계열)과 같은 대상을 둔 다른 주체들(공간), 선례, DX 시사점, 관찰 지표를 담은 HTML 보고서를 씁니다. 보고서는 팀 전체가 봅니다.
      </p>
    </form>
  );
}
