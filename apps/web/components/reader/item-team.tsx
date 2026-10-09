"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { collect, loadItemTeam, newCollection } from "@/app/(reader)/collections/actions";
import { TeamComments } from "@/components/reader/team-comments";
import { Button } from "@/components/ui/button";
import type { ItemTeam } from "@/lib/team-types";

const NEW = "__new__";

/** The team side of a card: memos and the shared collections that hold it (plan 16 #12). */
export function ItemTeamPanel({ itemId }: { itemId: number }) {
  const [team, setTeam] = useState<ItemTeam | null>(null);
  const [choice, setChoice] = useState("");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    loadItemTeam(itemId)
      .then(setTeam)
      .catch(() => setTeam({ comments: [], collections: [], all_collections: [] }));
  }, [itemId]);

  function save() {
    setMessage(null);
    startTransition(async () => {
      try {
        const detail = choice === NEW ? await newCollection(title, itemId) : await collect(Number(choice), itemId);
        setMessage(`'${detail.title}'에 담았습니다.`);
        setTeam(await loadItemTeam(itemId));
        setChoice("");
        setTitle("");
      } catch {
        setMessage("담지 못했습니다.");
      }
    });
  }

  if (!team) return <p className="text-xs text-muted-foreground">팀 메모를 불러오는 중…</p>;
  return (
    <div className="space-y-4 border-t pt-4">
      <TeamComments kind="item" targetId={itemId} initial={team.comments} />
      <section aria-label="공유 모음" className="space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">공유 모음</h3>
        {team.collections.length ? (
          <p className="flex flex-wrap gap-1.5 text-xs">
            {team.collections.map((c) => (
              <Link key={c.id} href={`/collections/${c.id}`} className="rounded-full border px-2 py-0.5 hover:bg-muted">
                {c.title}
              </Link>
            ))}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <label htmlFor={`collect-${itemId}`} className="sr-only">
            모음 고르기
          </label>
          <select id={`collect-${itemId}`} value={choice} onChange={(e) => setChoice(e.target.value)} className="h-9 max-w-[14rem] rounded-md border bg-background px-2 text-sm">
            <option value="">모음에 담기…</option>
            {team.all_collections
              .filter((c) => !team.collections.some((h) => h.id === c.id))
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            <option value={NEW}>+ 새 모음</option>
          </select>
          {choice === NEW ? (
            <input aria-label="새 모음 이름" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="모음 이름" className="h-9 rounded-md border bg-background px-2 text-sm" />
          ) : null}
          <Button type="button" size="sm" variant="outline" disabled={pending || !choice || (choice === NEW && title.trim().length < 2)} onClick={save}>
            담기
          </Button>
        </div>
        {message ? <p role="status" className="text-xs text-muted-foreground">{message}</p> : null}
      </section>
    </div>
  );
}
