"use client";

import { ChevronDown, ChevronRight, GripVertical } from "lucide-react";
import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { formatNumber } from "@/lib/format";
import { PRIORITY_LABEL } from "@/lib/taxonomy-ops";
import { cn } from "@/lib/utils";

import { type ConsoleNode, type ConsoleScheme, type Counts, type DropPosition, childrenOf, isInside, levelName, visibleIds } from "./model";

const STATUS: Record<string, string> = { deprecated: "비활성", merged: "통합됨", draft: "초안" };

/** Where in a row the pointer is: the top quarter places before, the bottom quarter after,
 * the middle puts the node inside (as a child). */
function positionIn(event: React.DragEvent<HTMLElement>): DropPosition {
  const rect = event.currentTarget.getBoundingClientRect();
  const y = (event.clientY - rect.top) / Math.max(rect.height, 1);
  return y < 0.25 ? "before" : y > 0.75 ? "after" : "inside";
}

/** Any-depth tree: expand, search, select, and drag a node above, below or onto another to
 * change its order and level. Moves go into the draft and show here at once (이동 예정). */
export function TaxonomyTree({
  scheme,
  counts,
  selected,
  onSelect,
  onMove,
  showInactive,
  moved = new Set<number>(),
}: {
  scheme: ConsoleScheme;
  counts: Counts;
  selected: number | null;
  onSelect: (node: ConsoleNode) => void;
  onMove: (node: ConsoleNode, parent: ConsoleNode | null, place?: { before?: ConsoleNode; after?: ConsoleNode }) => void;
  showInactive: boolean;
  moved?: Set<number>;
}) {
  const nodes = useMemo(() => scheme.nodes.filter((n) => showInactive || n.status === "active"), [scheme.nodes, showInactive]);
  const children = useMemo(() => childrenOf(nodes), [nodes]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Set<number>>(() => new Set(nodes.filter((n) => n.depth === 1).map((n) => n.id)));
  const [dragging, setDragging] = useState<ConsoleNode | null>(null);
  const [hint, setHint] = useState<{ id: number; position: DropPosition } | null>(null);
  const visible = useMemo(() => visibleIds(nodes, query), [nodes, query]);
  const tree = scheme.structure === "tree";

  const toggle = (id: number) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  /** A drop is allowed unless it would put the node inside itself or change nothing. */
  const allowed = (target: ConsoleNode, position: DropPosition): boolean => {
    if (!dragging || !tree || dragging.id === target.id) return false;
    const parent = position === "inside" ? target : target.parent_id ? byId.get(target.parent_id) ?? null : null;
    if (parent && isInside(nodes, dragging, parent)) return false;
    return !(position === "inside" && target.id === dragging.parent_id);
  };

  const finish = () => {
    setDragging(null);
    setHint(null);
  };

  const drop = (target: ConsoleNode | null, position: DropPosition = "inside") => {
    if (!dragging || !tree) return finish();
    if (target === null) {
      if (dragging.parent_id !== null) onMove(dragging, null);
      return finish();
    }
    if (!allowed(target, position)) return finish();
    if (position === "inside") onMove(dragging, target);
    else onMove(dragging, target.parent_id ? byId.get(target.parent_id) ?? null : null, { [position]: target });
    finish();
  };

  /** "3단계 기술로" — the level the dragged node would land on. */
  const landing = (target: ConsoleNode, position: DropPosition): string => {
    const depth = position === "inside" ? target.depth + 1 : target.depth;
    const where = position === "inside" ? `${target.label} 안` : `${target.label} ${position === "before" ? "앞" : "뒤"}`;
    const change = dragging && dragging.depth !== depth ? ` · ${dragging.depth}→${depth}단계` : "";
    return `${where} · ${levelName(scheme, depth)}${change}`;
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
              data-node-key={node.key}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", node.key);
                setDragging(node);
              }}
              onDragEnd={finish}
              onDragOver={(event) => {
                const position = positionIn(event);
                if (!allowed(node, position)) {
                  if (hint?.id === node.id) setHint(null);
                  return;
                }
                event.preventDefault();
                if (hint?.id !== node.id || hint.position !== position) setHint({ id: node.id, position });
              }}
              onDragLeave={() => hint?.id === node.id && setHint(null)}
              onDrop={(event) => {
                event.preventDefault();
                drop(node, positionIn(event));
              }}
              className={cn(
                "group relative flex items-center gap-1 rounded-md py-1 pr-2 text-sm hover:bg-muted",
                selected === node.id && "bg-primary/10 font-medium",
                node.status !== "active" && "text-muted-foreground line-through decoration-muted-foreground/40",
                dragging?.id === node.id && "opacity-50",
                hint?.id === node.id && hint.position === "inside" && "bg-primary/15 ring-2 ring-primary",
                hint?.id === node.id && hint.position === "before" && "shadow-[inset_0_2px_0_0_var(--color-primary)]",
                hint?.id === node.id && hint.position === "after" && "shadow-[inset_0_-2px_0_0_var(--color-primary)]",
              )}
              style={{ paddingLeft: `${(node.depth - 1) * 16 + 4}px` }}
            >
              {hint?.id === node.id ? (
                <span role="status" className="pointer-events-none absolute -top-5 right-1 z-10 rounded bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground shadow">
                  {landing(node, hint.position)}
                </span>
              ) : null}
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
              {moved.has(node.id) ? <span className="rounded bg-sky-500/15 px-1 text-[10px] text-sky-700 dark:text-sky-300" title="변경 초안에 이동이 담겼습니다 (적용 전)">이동 예정</span> : null}
              {node.edited_in_console ? <span className="rounded bg-primary/10 px-1 text-[10px] text-primary">콘솔</span> : null}
              {node.attrs.priority !== undefined && Number(node.attrs.priority) !== 1 ? (
                <span className={cn("rounded px-1 text-[10px]", Number(node.attrs.priority) === 0 ? "bg-destructive/10 text-destructive" : "bg-amber-500/15 text-amber-700 dark:text-amber-300")} title="카드화 우선순위">
                  {PRIORITY_LABEL[String(node.attrs.priority)] ?? String(node.attrs.priority)}
                </span>
              ) : null}
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
        {tree ? " · 끌어서 행 가운데에 놓으면 그 안(하위)으로, 위·아래 가장자리에 놓으면 그 앞·뒤(같은 단계)로" : ""}
      </p>
      {tree ? (
        // always in the layout (hidden until a drag) so rows do not shift when a drag starts
        <div
          aria-hidden={!dragging}
          onDragOver={(event) => dragging && event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            drop(null);
          }}
          className={cn("rounded-md border border-dashed p-2 text-center text-xs text-muted-foreground", !dragging && "invisible")}
        >
          여기에 놓으면 최상위({levelName(scheme, 1)})로
        </div>
      ) : null}
      <ul role="tree" aria-label={`${scheme.name} 트리`} className="max-h-[65vh] overflow-y-auto">
        {rows(null)}
      </ul>
    </div>
  );
}
