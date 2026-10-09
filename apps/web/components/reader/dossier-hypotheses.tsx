"use client";

import { ExternalLink, Lightbulb, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useState, useTransition } from "react";

import { addEvidence, addHypothesis, deleteEvidence, deleteHypothesis, suggestEvidence, updateHypothesis } from "@/app/(reader)/dossiers/actions";
import { Button } from "@/components/ui/button";
import { type Hypothesis, type HypothesisStatus, type Stance, STANCE_LABEL, STATUS_LABEL, type Suggestion } from "@/lib/dossier-types";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const STANCE_STYLE: Record<Stance, string> = {
  support: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  oppose: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  context: "border-border bg-muted text-muted-foreground",
};

export function DossierHypotheses({ dossierId, initial }: { dossierId: number; initial: Hypothesis[] }) {
  const [hypotheses, setHypotheses] = useState(initial);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function run(task: () => Promise<Hypothesis[]>) {
    setError(null);
    startTransition(async () => {
      try {
        setHypotheses(await task());
      } catch {
        setError("저장하지 못했습니다. 잠시 후 다시 시도하세요.");
      }
    });
  }

  return (
    <section aria-labelledby="hypotheses-heading" className="space-y-3">
      <h2 id="hypotheses-heading" className="text-base font-semibold">
        가설과 근거
      </h2>
      {hypotheses.length === 0 ? <p className="text-sm text-muted-foreground">확인하려는 주장을 가설로 적고, 카드를 찬성·반대·참고 근거로 붙이세요.</p> : null}
      {hypotheses.map((h) => (
        <HypothesisCard key={h.id} dossierId={dossierId} hypothesis={h} run={run} pending={pending} />
      ))}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (draft.trim().length < 4) return;
          const text = draft;
          setDraft("");
          run(() => addHypothesis(dossierId, text));
        }}
      >
        <label htmlFor="new-hypothesis" className="sr-only">
          새 가설
        </label>
        <input
          id="new-hypothesis"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={500}
          placeholder="예: 2027년까지 플래그십 스마트폰 대부분이 10B급 모델을 기기에서 돌린다"
          className="h-9 flex-1 rounded-md border bg-background px-3 text-sm"
        />
        <Button type="submit" size="sm" disabled={pending || draft.trim().length < 4}>
          가설 추가
        </Button>
      </form>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function HypothesisCard({
  dossierId,
  hypothesis: h,
  run,
  pending,
}: {
  dossierId: number;
  hypothesis: Hypothesis;
  run: (task: () => Promise<Hypothesis[]>) => void;
  pending: boolean;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [loading, startLoading] = useTransition();

  return (
    <article className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-start gap-2">
        <p className="min-w-0 flex-1 text-sm font-medium">{h.text}</p>
        <select
          aria-label="가설 판단"
          value={h.status}
          disabled={pending}
          onChange={(e) => run(() => updateHypothesis(dossierId, h.id, { status: e.target.value as HypothesisStatus }))}
          className="h-8 rounded-md border bg-background px-2 text-xs"
        >
          {(Object.keys(STATUS_LABEL) as HypothesisStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label="가설 삭제"
          disabled={pending}
          onClick={() => {
            if (window.confirm("이 가설과 붙인 근거를 지울까요?")) run(() => deleteHypothesis(dossierId, h.id));
          }}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="size-4" aria-hidden />
        </button>
      </div>
      <p className="text-xs text-muted-foreground">
        찬성 {h.counts.support} · 반대 {h.counts.oppose} · 참고 {h.counts.context}
      </p>
      {h.evidence.length ? (
        <ul className="space-y-1">
          {h.evidence.map((e) => (
            <li key={e.id} className="flex items-start gap-2 text-sm">
              <span className={cn("shrink-0 rounded border px-1.5 text-[11px]", STANCE_STYLE[e.stance])}>{STANCE_LABEL[e.stance]}</span>
              <div className="min-w-0 flex-1">
                <Link href={`/items/${e.item_id}`} scroll={false} className="line-clamp-1 hover:underline">
                  {e.title}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {e.source} · {formatDateTime(e.first_seen_at)}
                  {e.added_by ? ` · ${e.added_by}` : ""}
                  {e.note ? ` · ${e.note}` : ""}
                </p>
              </div>
              <button type="button" aria-label="근거 빼기" disabled={pending} onClick={() => run(() => deleteEvidence(dossierId, e.id))} className="text-muted-foreground hover:text-destructive">
                <X className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={loading}
        onClick={() => startLoading(async () => setSuggestions(await suggestEvidence(dossierId, h.id).catch(() => [])))}
      >
        <Lightbulb className="size-4" aria-hidden />
        {loading ? "찾는 중…" : "근거 후보 찾기"}
      </Button>
      {suggestions ? (
        suggestions.length ? (
          <ul aria-label="근거 후보" className="space-y-1.5 rounded-md bg-muted/40 p-2">
            {suggestions.map((s) => (
              <li key={s.item_id} className="flex flex-wrap items-center gap-2 text-sm">
                <div className="min-w-0 flex-1">
                  <Link href={`/items/${s.item_id}`} scroll={false} className="line-clamp-1 hover:underline">
                    {s.title}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {s.source} · {formatDateTime(s.first_seen_at)} · 유사도 {s.similarity.toFixed(2)}
                    <a href={s.url} target="_blank" rel="noreferrer noopener" aria-label="원문 열기" className="ml-1 inline-block align-middle">
                      <ExternalLink className="size-3" aria-hidden />
                    </a>
                  </p>
                </div>
                {(Object.keys(STANCE_LABEL) as Stance[]).map((stance) => (
                  <button
                    key={stance}
                    type="button"
                    disabled={pending}
                    onClick={() => {
                      setSuggestions((current) => current?.filter((c) => c.item_id !== s.item_id) ?? null);
                      run(() => addEvidence(dossierId, h.id, s.item_id, stance));
                    }}
                    className={cn("rounded border px-2 py-0.5 text-xs", STANCE_STYLE[stance])}
                  >
                    {STANCE_LABEL[stance]}
                  </button>
                ))}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">후보가 없습니다. 임베딩 모델이 꺼져 있거나 주제 파일에 맞는 카드가 아직 적습니다.</p>
        )
      ) : null}
    </article>
  );
}
