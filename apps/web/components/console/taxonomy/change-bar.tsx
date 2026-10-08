"use client";

import { X } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { applyChanges, previewChanges } from "@/app/console/taxonomy/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatNumber } from "@/lib/format";
import { type ChangeResult, describe, type Labeler, type TaxOp } from "@/lib/taxonomy-ops";

/** The draft change set: review, preview the real impact, apply as one revision. */
export function ChangeBar({ ops, label, onRemove, onClear }: { ops: TaxOp[]; label: Labeler; onRemove: (index: number) => void; onClear: () => void }) {
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ChangeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  if (!ops.length && !result) {
    return <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">변경 초안이 비어 있습니다. 트리에서 노드를 고르고 작업을 추가하세요. 적용 전에는 아무것도 바뀌지 않습니다.</p>;
  }
  const run = (apply: boolean) =>
    start(async () => {
      setError(null);
      const response = apply ? await applyChanges(ops, note) : await previewChanges(ops);
      if (!response.ok) {
        setError(response.error);
        setResult(null);
        return;
      }
      setResult(response.result);
      if (apply) {
        toast.success(`적용했습니다 (리비전 #${response.result.revision_id})`);
        onClear();
        setNote("");
      }
    });
  return (
    <section aria-label="변경 초안" className="space-y-3 rounded-lg border bg-card p-3">
      {ops.length ? (
        <>
          <ol className="space-y-1 text-sm">
            {ops.map((op, index) => (
              <li key={index} className="flex items-center gap-2">
                <span className="w-5 text-xs text-muted-foreground tabular-nums">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate">{describe(op, label)}</span>
                <button type="button" aria-label={`${index + 1}번 작업 빼기`} onClick={() => { onRemove(index); setResult(null); }} className="rounded p-0.5 text-muted-foreground hover:bg-muted">
                  <X className="size-3.5" aria-hidden />
                </button>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="변경 메모 (이력에 남습니다)" aria-label="변경 메모" className="h-8 min-w-48 flex-1" />
            <Button size="sm" variant="outline" disabled={pending} onClick={() => run(false)}>
              미리보기
            </Button>
            <Button size="sm" disabled={pending || !result || result.revision_id !== null} onClick={() => run(true)} title={result ? undefined : "먼저 미리보기로 영향을 확인하세요"}>
              적용
            </Button>
            <Button size="sm" variant="ghost" disabled={pending} onClick={() => { onClear(); setResult(null); }}>
              비우기
            </Button>
          </div>
        </>
      ) : null}
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {result ? (
        <div className="space-y-2 rounded-md bg-muted/40 p-2 text-sm" aria-label={result.revision_id ? "적용 결과" : "미리보기 결과"}>
          <p className="font-medium">
            {result.revision_id ? `적용됨 · 리비전 #${result.revision_id}` : "미리보기 (아직 적용 안 됨)"} · 영향 카드 {formatNumber(result.affected_cards)}
            {result.requeued_cards ? ` · 재분류 ${formatNumber(result.requeued_cards)}건${result.eta_hours !== null ? ` (약 ${result.eta_hours}시간)` : ""}` : " · 재분류 없음"}
          </p>
          <ul className="space-y-0.5 text-xs">
            {result.outcomes.map((o, i) => (
              <li key={i}>
                {o.summary} — 카드 {formatNumber(o.cards)}
                {o.requeued ? `, 재분류 ${formatNumber(o.requeued)}` : ""}
                {o.warnings.map((w) => (
                  <span key={w} className="block text-amber-700 dark:text-amber-300">
                    {w}
                  </span>
                ))}
              </li>
            ))}
          </ul>
          <p className={`text-xs ${result.prompt_over_budget ? "text-destructive" : "text-muted-foreground"}`}>
            분류 프롬프트 약 {formatNumber(result.prompt_tokens)} 토큰{result.prompt_over_budget ? " — Qwen 예산(6천)을 넘습니다. LLM 깊이 노드를 줄이세요." : ""}
          </p>
          {result.samples.length ? <p className="truncate text-xs text-muted-foreground">예: {result.samples.map((s) => s.title).filter(Boolean).join(" · ")}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
