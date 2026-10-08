"use client";

import { useState } from "react";

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
}

/** Phrases the classifier proposed when no theme fit: turn one into a node anywhere in a tree. */
export function CandidateInbox({ candidates, schemes, onAdd }: { candidates: Candidate[]; schemes: ConsoleScheme[]; onAdd: (op: TaxOp) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const [scheme, setScheme] = useState(schemes.find((s) => s.structure === "tree")?.key ?? schemes[0]?.key ?? "technology");
  const target = schemes.find((s) => s.key === scheme);
  if (!candidates.length) return <p className="text-sm text-muted-foreground">최근 30일 미분류 신호가 없습니다.</p>;
  return (
    <ul className="divide-y rounded-lg border">
      {candidates.map((c) => (
        <li key={c.key} className="space-y-2 p-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="min-w-0 flex-1 truncate font-medium">{c.label}</span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {formatNumber(c.count)}건 · 최근 7일 {formatNumber(c.recent)}
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
                  onAdd({ op: "create_node", scheme, key: suggestKey(c.label) || c.key, label: c.label, parent: parent?.key ?? null, aliases: [c.label] });
                  setOpen(null);
                }}
              />
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
