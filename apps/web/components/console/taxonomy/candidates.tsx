"use client";

import { useState, useTransition } from "react";

import { candidateClusters } from "@/app/console/taxonomy/actions";

import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import { suggestKey, type TaxOp } from "@/lib/taxonomy-ops";

import type { ConsoleScheme } from "./model";
import { NodePicker } from "./node-picker";

export interface Candidate {
  key: string;
  label: string;
  count: number;
  recent: number;
  phrases?: string[]; // grouped view: every phrase in the group (they become aliases)
}

/** Phrases the classifier proposed when no theme fit: turn one into a node anywhere in a tree. */
export function CandidateInbox({ candidates, schemes, onAdd }: { candidates: Candidate[]; schemes: ConsoleScheme[]; onAdd: (op: TaxOp) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const [scheme, setScheme] = useState(schemes.find((s) => s.structure === "tree")?.key ?? schemes[0]?.key ?? "technology");
  const target = schemes.find((s) => s.key === scheme);
  const [groups, setGroups] = useState<Candidate[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [pending, start] = useTransition();
  if (!candidates.length) return <p className="text-sm text-muted-foreground">최근 30일 미분류 신호가 없습니다.</p>;
  const rows = groups ?? candidates;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant={groups ? "default" : "outline"}
          disabled={pending}
          onClick={() =>
            groups
              ? setGroups(null)
              : start(async () => {
                  const result = await candidateClusters();
                  if (!result.ok) {
                    setNote(result.error);
                    return;
                  }
                  setNote(`${result.clusters.reduce((n, c) => n + c.phrases.length, 0)}개 표현 → ${result.clusters.length}개 묶음`);
                  setGroups(result.clusters.map((c) => ({ key: c.phrases[0].key, label: c.label, count: c.count, recent: 0, phrases: c.phrases.map((p) => p.label) })));
                })
          }
        >
          {groups ? "묶음 풀기" : "뜻이 같은 표현 묶기"}
        </Button>
        {note ? <span className="text-xs text-muted-foreground">{note}</span> : null}
      </div>
    <ul className="divide-y rounded-lg border">
      {rows.map((c) => (
        <li key={c.key} className="space-y-2 p-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="min-w-0 flex-1 truncate font-medium">{c.label}</span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {formatNumber(c.count)}건{groups ? ` · ${c.phrases?.length ?? 1}개 표현` : ` · 최근 7일 ${formatNumber(c.recent)}`}
            </span>
            <Button size="sm" variant="outline" onClick={() => setOpen(open === c.key ? null : c.key)}>
              노드로 추가
            </Button>
          </div>
          {open === c.key ? (
            <div className="space-y-2">
              <select value={scheme} onChange={(e) => setScheme(e.target.value)} aria-label="추가할 체계" className="h-8 rounded-md border bg-background px-2 text-sm">
                {schemes.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.name}
                  </option>
                ))}
              </select>
              <NodePicker
                label="상위 노드"
                allowRoot
                nodes={target?.nodes ?? []}
                onPick={(parent) => {
                  onAdd({ op: "create_node", scheme, key: suggestKey(c.label) || c.key, label: c.label, parent: parent?.key ?? null, aliases: c.phrases ?? [c.label] });
                  setOpen(null);
                }}
              />
            </div>
          ) : null}
          {groups && c.phrases && c.phrases.length > 1 ? <p className="text-xs text-muted-foreground">{c.phrases.join(" · ")}</p> : null}
        </li>
      ))}
    </ul>
    </div>
  );
}
