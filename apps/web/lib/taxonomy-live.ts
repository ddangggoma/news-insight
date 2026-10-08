// The classification schemes from the database (plan 15-4). Server and browser code import the
// label records from @/lib/taxonomy as before; applyTaxonomy() updates them in place with what
// the console has renamed or added, so every page follows without each one fetching. Keys that
// left the schemes keep their last label (old cards still carry them).
import { FIELD_LABEL, IMPACT_LABEL, SCOPE_LABEL, SIGNAL_LABEL, THEME_LABEL } from "@/lib/taxonomy";

export interface SchemeNode {
  id: number;
  key: string;
  label: string;
  parent_id: number | null;
  depth: number;
  status: string;
  sort: number;
}

export interface SchemeView {
  key: string;
  name: string;
  structure: "tree" | "list";
  min_labels: number;
  max_labels: number;
  llm_depth: number | null;
  level_names: string[];
  uses: string[];
  nodes: SchemeNode[];
}

export interface TaxonomySchemes {
  revision: number | null;
  schemes: SchemeView[];
}

/** Every node of every scheme, keyed `scheme:key`. */
export const NODE_LABEL: Record<string, string> = {};
const LIST_LABELS: Record<string, Record<string, string>> = { signal_type: SIGNAL_LABEL, impact: IMPACT_LABEL, scope: SCOPE_LABEL };
let applied: number | null | undefined;

export function applyTaxonomy(taxonomy: TaxonomySchemes | null | undefined): void {
  if (!taxonomy || (applied !== undefined && applied === taxonomy.revision)) return;
  for (const scheme of taxonomy.schemes) {
    for (const node of scheme.nodes) {
      NODE_LABEL[`${scheme.key}:${node.key}`] = node.label;
      if (scheme.key === "technology") {
        if (node.depth === 1) FIELD_LABEL[node.key] = node.label;
        if (node.depth === 2) THEME_LABEL[node.key] = node.label;
      } else if (LIST_LABELS[scheme.key]) {
        LIST_LABELS[scheme.key][node.key] = node.label;
      }
    }
  }
  applied = taxonomy.revision;
}

/** Nodes as an indented option list (any depth), parents before children. */
export function nodeOptions(scheme: SchemeView): { value: string; label: string; depth: number }[] {
  const children = new Map<number | null, SchemeNode[]>();
  for (const node of scheme.nodes) children.set(node.parent_id, [...(children.get(node.parent_id) ?? []), node]);
  const out: { value: string; label: string; depth: number }[] = [];
  const walk = (parent: number | null) => {
    for (const node of (children.get(parent) ?? []).sort((a, b) => a.sort - b.sort || a.id - b.id)) {
      out.push({ value: `${scheme.key}:${node.key}`, label: node.label, depth: node.depth });
      walk(node.id);
    }
  };
  walk(null);
  return out;
}
