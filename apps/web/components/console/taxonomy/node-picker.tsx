"use client";

import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";

import { type ConsoleNode, pathLabel } from "./model";

/** Search a scheme's nodes by name, key or alias and pick one (or the top level). */
export function NodePicker({
  nodes,
  exclude = () => false,
  allowRoot = false,
  onPick,
  label,
}: {
  nodes: ConsoleNode[];
  exclude?: (node: ConsoleNode) => boolean;
  allowRoot?: boolean;
  onPick: (node: ConsoleNode | null) => void;
  label: string;
}) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return nodes
      .filter((n) => n.status === "active" && !exclude(n))
      .filter((n) => !q || [n.label, n.key, ...n.aliases].join(" ").toLowerCase().includes(q))
      .slice(0, 30);
  }, [nodes, query, exclude]);
  return (
    <div className="space-y-1.5">
      <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`${label} 검색`} aria-label={label} className="h-8" />
      <ul className="max-h-48 overflow-y-auto rounded-md border text-sm">
        {allowRoot ? (
          <li>
            <button type="button" onClick={() => onPick(null)} className="w-full px-2 py-1 text-left hover:bg-muted">
              (최상위)
            </button>
          </li>
        ) : null}
        {matches.map((node) => (
          <li key={node.id}>
            <button type="button" onClick={() => onPick(node)} className="w-full px-2 py-1 text-left hover:bg-muted">
              <span className="block truncate">{node.label}</span>
              <span className="block truncate text-[11px] text-muted-foreground">{pathLabel(nodes, node)}</span>
            </button>
          </li>
        ))}
        {!matches.length ? <li className="px-2 py-1 text-xs text-muted-foreground">맞는 노드가 없습니다</li> : null}
      </ul>
    </div>
  );
}
