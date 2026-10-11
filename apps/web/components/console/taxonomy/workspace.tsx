"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Revision, TaxOp } from "@/lib/taxonomy-ops";

import { type Candidate, CandidateInbox } from "./candidates";
import { ChangeBar } from "./change-bar";
import { TaxonomyGuide } from "./guide";
import { RevisionHistory } from "./history";
import { NodeInspector } from "./inspector";
import { applyMoves, type ConsoleNode, type ConsoleScheme, type Counts } from "./model";
import { SchemePanel } from "./scheme-panel";
import { TaxonomyTree } from "./tree";

const DRAFT_KEY = "taxonomy-draft-v1";

function readDraft(): TaxOp[] {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as TaxOp[]) : [];
  } catch {
    return [];
  }
}

/** The console's taxonomy workspace (plan 15-5): schemes, any-depth trees, one change set. */
export function TaxonomyWorkspace({ schemes, current, counts, revisions, candidates }: { schemes: ConsoleScheme[]; current: string; counts: Counts; revisions: Revision[]; candidates: Candidate[] }) {
  const scheme = schemes.find((s) => s.key === current) ?? schemes[0];
  const [ops, setOps] = useState<TaxOp[]>([]);
  const [selected, setSelected] = useState<ConsoleNode | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  useEffect(() => setOps(readDraft()), []);
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(ops));
    } catch {
      // private mode: the draft lives as long as the page
    }
  }, [ops]);
  useEffect(() => setSelected((s) => (s ? scheme?.nodes.find((n) => n.id === s.id) ?? null : null)), [scheme]);

  const labels = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of schemes) for (const n of s.nodes) map.set(`${s.key}:${n.key}`, n.label);
    return map;
  }, [schemes]);
  const label = (s: string, k: string) => labels.get(`${s}:${k}`) ?? k;
  // the tree shows the draft's moves before they are applied
  const preview = useMemo(() => (scheme ? applyMoves(scheme.nodes, ops, scheme.key) : null), [scheme, ops]);
  const shown = useMemo(() => (scheme && preview ? { ...scheme, nodes: preview.nodes } : scheme), [scheme, preview]);
  const add = (op: TaxOp) => setOps((prev) => [...prev, op]);

  if (!scheme) return <p className="text-sm text-muted-foreground">체계가 없습니다. `news-insight taxonomy seed`를 먼저 실행하세요.</p>;
  return (
    <div className="space-y-4">
      <nav aria-label="체계" className="flex flex-wrap gap-2">
        {schemes.map((s) => (
          <Link key={s.key} href={`/console/taxonomy?scheme=${s.key}`} aria-current={s.key === scheme.key ? "page" : undefined} className="rounded-full border px-3 py-1 text-sm aria-[current=page]:border-primary aria-[current=page]:bg-primary/10 aria-[current=page]:font-semibold">
            {s.name} <span className="text-xs text-muted-foreground">{s.nodes.filter((n) => n.status === "active").length}</span>
          </Link>
        ))}
      </nav>
      <ChangeBar ops={ops} label={label} onRemove={(i) => setOps((prev) => prev.filter((_, j) => j !== i))} onClear={() => setOps([])} />
      <Tabs defaultValue="tree">
        <TabsList>
          <TabsTrigger value="tree">트리</TabsTrigger>
          <TabsTrigger value="scheme">체계 설정</TabsTrigger>
          <TabsTrigger value="history">이력</TabsTrigger>
          <TabsTrigger value="candidates">후보 {candidates.length ? <span className="ml-1 text-xs text-muted-foreground">{candidates.length}</span> : null}</TabsTrigger>
          <TabsTrigger value="guide">사용법</TabsTrigger>
        </TabsList>
        <TabsContent value="tree" className="pt-3">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <div className="min-w-0 space-y-2 rounded-lg border p-3">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> 비활성·통합 노드도 보기
              </label>
              <TaxonomyTree
                scheme={shown ?? scheme}
                moved={preview?.moved}
                counts={counts}
                selected={selected?.id ?? null}
                onSelect={setSelected}
                showInactive={showInactive}
                onMove={(node, parent, place) =>
                  add({ op: "move_node", scheme: scheme.key, key: node.key, parent: parent?.key ?? null, ...(place?.before ? { before: place.before.key } : {}), ...(place?.after ? { after: place.after.key } : {}) })
                }
              />
            </div>
            <div className="min-w-0 rounded-lg border p-3">
              {selected ? (
                <NodeInspector scheme={scheme} schemes={schemes} node={selected} counts={counts} onAdd={add} />
              ) : (
                <div className="space-y-3 text-sm text-muted-foreground">
                  <p>왼쪽 트리에서 노드를 고르세요.</p>
                  <button type="button" className="text-primary hover:underline" onClick={() => add({ op: "create_node", scheme: scheme.key, key: `new-${Date.now().toString(36)}`, label: "새 노드", parent: null })}>
                    최상위에 새 노드 추가 (이름은 추가 후 수정)
                  </button>
                </div>
              )}
            </div>
          </div>
        </TabsContent>
        <TabsContent value="scheme" className="pt-3">
          <SchemePanel key={scheme.key} scheme={scheme} assign={scheme.assign} onAdd={add} />
        </TabsContent>
        <TabsContent value="history" className="pt-3">
          <RevisionHistory revisions={revisions} label={label} />
        </TabsContent>
        <TabsContent value="guide" className="pt-3">
          <TaxonomyGuide />
        </TabsContent>
        <TabsContent value="candidates" className="pt-3">
          <CandidateInbox candidates={candidates} schemes={schemes} onAdd={add} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
