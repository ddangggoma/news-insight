"use client";

import { Trash2 } from "lucide-react";
import { useEffect, useState, useTransition } from "react";

import { addComment, deleteComment, loadComments } from "@/app/(reader)/collections/actions";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import type { CommentKind, TeamComment } from "@/lib/team-types";

/** A team thread on a card (its memos), a collection or a dossier (plan 16 #12). */
export function TeamComments({ kind, targetId, initial, title = "팀 메모" }: { kind: CommentKind; targetId: number; initial?: TeamComment[]; title?: string }) {
  const [comments, setComments] = useState<TeamComment[] | null>(initial ?? null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    if (initial) return;
    loadComments(kind, targetId)
      .then(setComments)
      .catch(() => setComments([]));
  }, [initial, kind, targetId]);

  function run(task: () => Promise<TeamComment[]>) {
    setError(null);
    startTransition(async () => {
      try {
        setComments(await task());
      } catch {
        setError("저장하지 못했습니다.");
      }
    });
  }

  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-sm font-semibold text-muted-foreground">
        {title} {comments?.length ? comments.length : ""}
      </h3>
      {comments === null ? <p className="text-xs text-muted-foreground">불러오는 중…</p> : null}
      <ul className="space-y-1.5">
        {(comments ?? []).map((c) => (
          <li key={c.id} className="rounded-md bg-muted/40 px-2.5 py-1.5 text-sm">
            <p className="whitespace-pre-wrap">{c.body}</p>
            <p className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
              {c.author ?? "알 수 없음"} · {formatDateTime(c.created_at)}
              {c.mine ? (
                <button type="button" aria-label="메모 지우기" disabled={pending} onClick={() => run(() => deleteComment(c.id))} className="ml-auto hover:text-destructive">
                  <Trash2 className="size-3.5" aria-hidden />
                </button>
              ) : null}
            </p>
          </li>
        ))}
      </ul>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!draft.trim()) return;
          const body = draft;
          setDraft("");
          run(() => addComment(kind, targetId, body));
        }}
      >
        <label htmlFor={`comment-${kind}-${targetId}`} className="sr-only">
          {title} 쓰기
        </label>
        <input id={`comment-${kind}-${targetId}`} value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={2000} placeholder="팀에 남길 메모" className="h-9 flex-1 rounded-md border bg-background px-3 text-sm" />
        <Button type="submit" size="sm" variant="outline" disabled={pending || !draft.trim()}>
          남기기
        </Button>
      </form>
      {error ? <p role="alert" className="text-xs text-destructive">{error}</p> : null}
    </section>
  );
}
