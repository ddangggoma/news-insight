import type { ScopeOption } from "@/lib/ask-types";
import type { TaxonomySchemes } from "@/lib/taxonomy-live";

const SCOPE_SCHEMES = ["technology", "theme"];

/** Active technology and theme nodes down to the second level, parents before children. */
export function scopeOptions(taxonomy: TaxonomySchemes | null, maxDepth = 2): ScopeOption[] {
  const scopes: ScopeOption[] = [];
  for (const scheme of taxonomy?.schemes ?? []) {
    if (!SCOPE_SCHEMES.includes(scheme.key)) continue;
    const byId = new Map(scheme.nodes.map((node) => [node.id, node]));
    const nodes = scheme.nodes
      .filter((node) => node.status === "active" && node.depth <= maxDepth)
      .sort((a, b) => (a.parent_id ?? a.id) - (b.parent_id ?? b.id) || a.depth - b.depth || a.sort - b.sort);
    for (const node of nodes) {
      const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
      scopes.push({
        value: `${scheme.key}:${node.key}`,
        label: `${scheme.name} · ${parent ? `${parent.label} › ` : ""}${node.label}`,
      });
    }
  }
  return scopes;
}
