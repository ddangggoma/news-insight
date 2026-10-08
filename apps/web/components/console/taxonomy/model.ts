// Client-side helpers for the taxonomy workspace: the console's scheme view as a tree.

export interface ConsoleNode {
  id: number;
  key: string;
  label: string;
  parent_id: number | null;
  depth: number;
  status: string;
  sort: number;
  definition: string | null;
  include_text: string | null;
  exclude_text: string | null;
  aliases: string[];
  attrs: Record<string, unknown>;
  merged_into_id: number | null;
  edited_in_console: boolean;
}

export interface ConsoleScheme {
  key: string;
  name: string;
  structure: "tree" | "list";
  min_labels: number;
  max_labels: number;
  llm_depth: number | null;
  level_names: string[];
  uses: string[];
  assign: ("llm" | "rule" | "derived")[];
  description: string | null;
  nodes: ConsoleNode[];
}

export type Counts = Record<string, { own: number; total: number }>;

export function childrenOf(nodes: ConsoleNode[]): Map<number | null, ConsoleNode[]> {
  const map = new Map<number | null, ConsoleNode[]>();
  for (const node of nodes) map.set(node.parent_id, [...(map.get(node.parent_id) ?? []), node]);
  for (const list of map.values()) list.sort((a, b) => a.sort - b.sort || a.label.localeCompare(b.label, "ko"));
  return map;
}

/** Ids of nodes matching the query plus all their ancestors, or null when there is no query. */
export function visibleIds(nodes: ConsoleNode[], query: string): Set<number> | null {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const out = new Set<number>();
  for (const node of nodes) {
    const hay = [node.label, node.key, ...node.aliases].join(" ").toLowerCase();
    if (!hay.includes(q)) continue;
    let cursor: ConsoleNode | undefined = node;
    while (cursor && !out.has(cursor.id)) {
      out.add(cursor.id);
      cursor = cursor.parent_id ? byId.get(cursor.parent_id) : undefined;
    }
  }
  return out;
}

/** True when `candidate` is `node` or lies below it (a move there would make a cycle). */
export function isInside(nodes: ConsoleNode[], node: ConsoleNode, candidate: ConsoleNode): boolean {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let cursor: ConsoleNode | undefined = candidate;
  while (cursor) {
    if (cursor.id === node.id) return true;
    cursor = cursor.parent_id ? byId.get(cursor.parent_id) : undefined;
  }
  return false;
}

export function pathLabel(nodes: ConsoleNode[], node: ConsoleNode): string {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const parts: string[] = [];
  let cursor: ConsoleNode | undefined = node;
  while (cursor) {
    parts.unshift(cursor.label);
    cursor = cursor.parent_id ? byId.get(cursor.parent_id) : undefined;
  }
  return parts.join(" › ");
}

export function levelName(scheme: ConsoleScheme, depth: number): string {
  return scheme.level_names[depth - 1] ?? `${depth}단계`;
}
