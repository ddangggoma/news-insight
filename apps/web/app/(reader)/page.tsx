import { BriefingAside } from "@/components/reader/briefing-aside";
import { BriefingMain } from "@/components/reader/briefing-main";
import { LatestFallback } from "@/components/reader/latest-fallback";
import { TaxonomyTree } from "@/components/reader/taxonomy-tree";
import { ThreePane } from "@/components/reader/three-pane";
import { reader } from "@/lib/reader";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [briefing, counts] = await Promise.all([reader.latest(), reader.taxonomy()]);
  if (!briefing) {
    const latest = await reader.cards({ days: 2, size: 30 });
    return (
      <ThreePane
        nav={<TaxonomyTree counts={counts} />}
        main={<LatestFallback cards={latest?.items ?? []} />}
        aside={<p className="text-sm text-muted-foreground">페르소나 통찰과 전략 요약은 첫 브리핑 발행 후 표시됩니다.</p>}
      />
    );
  }
  return <ThreePane nav={<TaxonomyTree counts={counts} />} main={<BriefingMain briefing={briefing} />} aside={<BriefingAside briefing={briefing} />} />;
}
