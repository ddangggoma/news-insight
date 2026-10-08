"use client";

import { useState, useTransition } from "react";

import { nodeMisfits, type SimilarCard, similarCards } from "@/app/console/taxonomy/actions";
import { Button } from "@/components/ui/button";

import type { ConsoleNode } from "./model";

/** Embedding help on a node (plan 15-6): what its name and definition would gather, and which of
 * its cards look out of place. */
export function EmbeddingHelp({ node }: { node: ConsoleNode }) {
  const [similar, setSimilar] = useState<{ cards: SimilarCard[]; unlabelled: number } | null>(null);
  const [odd, setOdd] = useState<Awaited<ReturnType<typeof nodeMisfits>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const query = [node.label, node.definition, node.include_text].filter(Boolean).join(". ");
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">임베딩 도움</h3>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={pending}
          onClick={() =>
            start(async () => {
              setError(null);
              const result = await similarCards(query, node.id);
              if (result.ok) setSimilar(result);
              else setError(result.error);
            })
          }
        >
          이름·정의와 비슷한 기사
        </Button>
        <Button size="sm" variant="outline" disabled={pending} onClick={() => start(async () => setOdd(await nodeMisfits(node.id)))}>
          어울리지 않는 카드
        </Button>
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
      {similar ? (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">상위 {similar.cards.length}건 중 이 노드에 아직 없는 카드 {similar.unlabelled}건 — 정의·별칭을 다듬을 근거입니다.</p>
          <ul className="space-y-0.5 text-sm" aria-label="비슷한 기사">
            {similar.cards.map((card) => (
              <li key={card.item_id} className="flex gap-2">
                <span className="w-10 shrink-0 text-[11px] text-muted-foreground tabular-nums">{card.similarity.toFixed(2)}</span>
                <a href={`/console/items/${card.item_id}`} className={`min-w-0 flex-1 truncate hover:underline ${card.labelled ? "" : "font-medium"}`}>
                  {card.title}
                </a>
                <span className="shrink-0 text-[11px] text-muted-foreground">{card.labelled ? "붙음" : "없음"}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {odd ? (
        odd.cards.length ? (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">
              카드 {odd.members}건의 중심과 가장 먼 카드 (평균 유사도 {odd.mean_similarity?.toFixed(2)}) — 잘못 분류됐을 수 있습니다.
            </p>
            <ul className="space-y-0.5 text-sm" aria-label="어울리지 않는 카드">
              {odd.cards.map((card) => (
                <li key={card.item_id} className="flex gap-2">
                  <span className="w-10 shrink-0 text-[11px] text-muted-foreground tabular-nums">{card.similarity.toFixed(2)}</span>
                  <a href={`/console/items/${card.item_id}`} className="min-w-0 flex-1 truncate hover:underline">
                    {card.title}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">임베딩이 있는 카드가 없습니다.</p>
        )
      ) : null}
    </section>
  );
}
