"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { rollbackRevision } from "@/app/console/taxonomy/actions";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/format";
import { describe, type Labeler, type Revision } from "@/lib/taxonomy-ops";

const STATUS: Record<string, string> = { applied: "적용", rolled_back: "되돌림", draft: "초안" };

/** Applied revisions, newest first, each with what it did and a rollback. */
export function RevisionHistory({ revisions, label }: { revisions: Revision[]; label: Labeler }) {
  const [pending, start] = useTransition();
  return (
    <ol className="space-y-3">
      {revisions.map((revision) => (
        <li key={revision.id} className="space-y-1 rounded-lg border p-3 text-sm">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">#{revision.id}</span>
            <span className="rounded bg-muted px-1.5 text-xs">{STATUS[revision.status] ?? revision.status}</span>
            <span className="text-xs text-muted-foreground">
              {revision.author ?? "—"} · {formatRelative(revision.created_at)}
            </span>
            {revision.status === "applied" && revision.ops.length ? (
              <Button
                size="sm"
                variant="outline"
                className="ml-auto h-7"
                disabled={pending}
                onClick={() => {
                  if (!window.confirm(`리비전 #${revision.id}을 되돌립니다. 계속할까요?`)) return;
                  start(async () => {
                    const response = await rollbackRevision(revision.id);
                    if (response.ok) toast.success(`되돌렸습니다 (새 리비전 #${response.result.revision_id})`);
                    else toast.error(response.error);
                  });
                }}
              >
                되돌리기
              </Button>
            ) : null}
          </p>
          {revision.note ? <p className="text-muted-foreground">{revision.note}</p> : null}
          {revision.ops.length ? (
            <ul className="list-disc pl-5 text-xs">
              {revision.ops.slice(0, 8).map((op, i) => (
                <li key={i}>{(op.op as string) === "restore_columns" ? "카드 컬럼 복원" : safeDescribe(op, label)}</li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function safeDescribe(op: Parameters<typeof describe>[0], label: Labeler): string {
  try {
    return describe(op, label) ?? op.op;
  } catch {
    return op.op;
  }
}
