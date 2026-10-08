"use client";

import { ChevronDown, ChevronRight, GripVertical } from "lucide-react";
import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { type ConsoleNode, type ConsoleScheme, type Counts, childrenOf, isInside, levelName, visibleIds } from "./model";

const STATUS: Record<string, string> = { deprecated: "비활성", merged: "통합됨", draft: "초안" };

/** Any-depth tree: expand, search, select, and drag a node onto another to move it there. */
export function TaxonomyTree({
  scheme,
  counts,
  selected,
  onSelect,
  onMove,
  showInactive,
}: {
  scheme: ConsoleScheme;
  counts: Counts;
  selected: number | null;
  onSelect: (node: ConsoleNode) => void;
  onMove: (node: ConsoleNode, parent: ConsoleNode | null) => void;
  showInactive: boolean;
}) {
  const nodes = useMemo(() => scheme.nodes.filter((n) => showInactive || n.status === "active"), [scheme.nodes, showInactive]);
  const children = useMemo(() => childrenOf(nodes), [nodes]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Set<number>>(() => new Set(nodes.filter((n) => n.depth === 1).map((n) => n.id)));
  const [dragging, setDragging] = useState<ConsoleNode | null>(null);
  const visible = useMemo(() => visibleIds(nodes, query), [nodes, query]);
  const tree = scheme.structure === "tree";

  const toggle = (id: number) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  const drop = (target: ConsoleNode | null) => {
    if (!dragging || !tree) return;
    if (target && isInside(nodes, dragging, target)) return;
    if ((target?.id ?? null) !== dragging.parent_id) onMove(dragging, target);
    setDragging(null);
  };

  const rows = (parent: number | null): React.ReactNode =>
    (children.get(parent) ?? [])
      .filter((node) => !visible || visible.has(node.id))
      .map((node) => {
        const kids = children.get(node.id) ?? [];
        const expanded = open.has(node.id) || visible !== null;
        const count = counts[String(node.id)];
        return (
          <li key={node.id} role="treeitem" aria-expanded={kids.length ? expanded : undefined} aria-selected={selected === node.id}>
            <div
              draggable={tree}
              onDragStart={() => setDragging(node)}
              onDragEnd={() => setDragging(null)}
              onDragOver={(event) => {
                if (dragging && dragging.id !== node.id && !isInside(nodes, dragging, node)) event.preventDefault();
              }}
              onDrop={(event) => {
                event.preventDefault();
                drop(node);
              }}
              className={cn(
                "group flex items-center gap-1 rounded-md py-1 pr-2 text-sm hover:bg-muted",
                selected === node.id && "bg-primary/10 font-medium",
                node.status !== "active" && "text-muted-foreground line-through decoration-muted-foreground/40",
              )}
              style={{ paddingLeft: `${(node.depth - 1) * 16 + 4}px` }}
            >
              {kids.length ? (
                <button type="button" aria-label={expanded ? `${node.label} 접기` : `${node.label} 펼치기`} onClick={() => toggle(node.id)} className="rounded p-0.5 hover:bg-background">
                  {expanded ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
                </button>
              ) : (
                <span className="inline-block w-[18px]" />
              )}
              {tree ? <GripVertical className="size-3 shrink-0 text-muted-foreground/50 opacity-0 group-hover:opacity-100" aria-hidden /> : null}
              <button type="button" onClick={() => onSelect(node)} className="min-w-0 flex-1 truncate text-left">
                {node.label}
                <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">{node.key}</span>
              </button>
              {STATUS[node.status] ? <span className="rounded bg-muted px-1 text-[10px]">{STATUS[node.status]}</span> : null}
              {node.edited_in_console ? <span className="rounded bg-primary/10 px-1 text-[10px] text-primary">콘솔</span> : null}
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums" title="30일 카드 (하위 포함 / 이 노드)">
                {count ? `${formatNumber(count.total)}${count.own !== count.total ? ` / ${formatNumber(count.own)}` : ""}` : "0"}
              </span>
            </div>
            {kids.length && expanded ? (
              <ul role="group">{rows(node.id)}</ul>
            ) : null}
          </li>
        );
      });

  return (
    <div className="space-y-2">
      <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="이름·키·별칭 검색" aria-label="노드 검색" className="h-8" />
      <p className="text-xs text-muted-foreground">
        깊이 이름: {Array.from({ length: Math.max(1, ...nodes.map((n) => n.depth)) }, (_, i) => levelName(scheme, i + 1)).join(" › ")}
        {scheme.llm_depth ? ` · LLM은 ${scheme.llm_depth}단계까지 고름` : ""}
        {tree ? " · 끌어다 놓으면 그 아래로 이동" : ""}
      </p>
      {tree && dragging ? (
        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            drop(null);
          }}
          className="rounded-md border border-dashed p-2 text-center text-xs text-muted-foreground"
        >
          여기에 놓으면 최상위로
        </div>
      ) : null}
      <ul role="tree" aria-label={`${scheme.name} 트리`} className="max-h-[65vh] overflow-y-auto">
        {rows(null)}
      </ul>
    </div>
  );
}
