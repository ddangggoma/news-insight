import { PageHeader } from "@/components/console/page-header";
import type { Candidate } from "@/components/console/taxonomy/candidates";
import type { ConsoleScheme, Counts } from "@/components/console/taxonomy/model";
import { TaxonomyWorkspace } from "@/components/console/taxonomy/workspace";
import { api } from "@/lib/api";
import { param, type SearchParams } from "@/lib/params";
import type { Revision } from "@/lib/taxonomy-ops";

export const metadata = { title: "분류 체계" };

export default async function TaxonomyPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const taxonomy = await api.get<{ revision: number | null; schemes: ConsoleScheme[] }>("/api/admin/taxonomy/schemes");
  const current = param(sp, "scheme") ?? taxonomy.schemes[0]?.key ?? "technology";
  const [counts, revisions, candidates] = await Promise.all([
    api.get<Counts>("/api/admin/taxonomy/counts", { scheme: current, days: 30 }).catch(() => ({}) as Counts),
    api.get<Revision[]>("/api/admin/taxonomy/revisions", { limit: 30 }).catch(() => []),
    api.get<Candidate[]>("/api/admin/topic-candidates", { days: 30, min_count: 3 }).catch(() => []),
  ]);
  return (
    <>
      <PageHeader
        title="분류 체계"
        description={`체계(분류의 종류)와 깊이 제한 없는 노드를 편집합니다. 변경은 초안에 쌓였다가 미리보기로 영향(카드 수·재분류·프롬프트 크기)을 확인한 뒤 한 번에 적용되고, 이력에서 되돌릴 수 있습니다. 현재 리비전 #${taxonomy.revision ?? "—"}.`}
      />
      <TaxonomyWorkspace schemes={taxonomy.schemes} current={current} counts={counts} revisions={revisions} candidates={candidates.slice(0, 40)} />
    </>
  );
}
