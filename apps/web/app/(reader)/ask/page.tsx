import type { Metadata } from "next";

import { AskPanel } from "@/components/reader/ask-panel";
import type { ScopeOption } from "@/lib/ask-types";
import { requireUser } from "@/lib/session";
import { loadTaxonomy } from "@/lib/taxonomy-server";

export const metadata: Metadata = { title: "질문하기", robots: { index: false } };

const SCOPE_SCHEMES = ["technology", "theme"];

export default async function AskPage() {
  await requireUser();
  const taxonomy = await loadTaxonomy();
  const scopes: ScopeOption[] = [];
  for (const scheme of taxonomy?.schemes ?? []) {
    if (!SCOPE_SCHEMES.includes(scheme.key)) continue;
    const byId = new Map(scheme.nodes.map((node) => [node.id, node]));
    const nodes = scheme.nodes
      .filter((node) => node.status === "active" && node.depth <= 2)
      .sort((a, b) => (a.parent_id ?? a.id) - (b.parent_id ?? b.id) || a.depth - b.depth || a.sort - b.sort);
    for (const node of nodes) {
      const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
      scopes.push({
        value: `${scheme.key}:${node.key}`,
        label: `${scheme.name} · ${parent ? `${parent.label} › ` : ""}${node.label}`,
      });
    }
  }
  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-xl font-semibold">질문하기</h1>
        <p className="text-sm text-muted-foreground">
          수집·카드화된 기사만 근거로 로컬 모델이 답합니다. 답의 [번호]는 아래 근거 기사로 이어집니다.
        </p>
      </div>
      <AskPanel scopes={scopes} />
    </main>
  );
}
