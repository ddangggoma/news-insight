import { Rss } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PaginationBar } from "@/components/console/pagination-bar";
import { CardList } from "@/components/reader/card-list";
import { TaxonomyTree, type TopicSelection } from "@/components/reader/taxonomy-tree";
import { ThreePane } from "@/components/reader/three-pane";
import { Button } from "@/components/ui/button";
import { withQuery } from "@/lib/query";
import { pageParam, param, type SearchParams } from "@/lib/params";
import { reader } from "@/lib/reader";
import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL, THEME_LABEL } from "@/lib/taxonomy";

export const metadata: Metadata = { title: "주제 탐색" };
export const dynamic = "force-dynamic";
const LABELS: Record<string, string> = { ...FIELD_LABEL, ...THEME_LABEL, ...BUSINESS_LABEL, ...IMPACT_LABEL };

function pick(params: SearchParams): TopicSelection {
  const valid = (value: string | undefined, labels: Record<string, string>) => (value && value in labels ? value : undefined);
  return {
    field: valid(param(params, "field"), FIELD_LABEL),
    theme: valid(param(params, "theme"), THEME_LABEL),
    business: valid(param(params, "business"), BUSINESS_LABEL),
    impact: valid(param(params, "impact"), IMPACT_LABEL),
  };
}

export default async function TopicsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const selected = pick(params);
  const page = pageParam(params);
  const node = selected.theme ?? selected.field ?? selected.business ?? selected.impact;
  const [counts, result] = await Promise.all([
    reader.taxonomy(),
    node ? reader.cards({ ...selected, days: 30, page, size: 30 }) : Promise.resolve(null),
  ]);
  const field = selected.field ?? selected.theme?.split("__")[0];
  const themes = field ? Object.keys(THEME_LABEL).filter((key) => key.startsWith(`${field}__`)) : [];
  const main = node ? (
    <div className="space-y-5">
      <header className="space-y-3">
        {selected.theme && field ? (
          <Link href={`/topics?field=${field}`} className="text-sm text-muted-foreground hover:text-foreground">
            {FIELD_LABEL[field]}
          </Link>
        ) : null}
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{LABELS[node] ?? node}</h1>
          <Button asChild variant="outline" size="sm" className="ml-auto">
            <a href={withQuery("/rss.xml", { ...selected })}>
              <Rss className="size-4" /> 이 주제 RSS
            </a>
          </Button>
        </div>
        {themes.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {themes.map((theme) => (
              <Link
                key={theme}
                href={`/topics?theme=${theme}`}
                aria-current={selected.theme === theme ? "page" : undefined}
                className="rounded-full border px-3 py-1 text-sm hover:bg-muted aria-[current=page]:border-primary aria-[current=page]:bg-primary/10 aria-[current=page]:text-primary"
              >
                {THEME_LABEL[theme]} <span className="text-xs text-muted-foreground">{counts.themes[theme] ?? 0}</span>
              </Link>
            ))}
          </div>
        ) : null}
        <p className="text-sm text-muted-foreground">최근 30일 · 같은 이슈는 대표 기사 하나로 묶음 · {result?.total ?? 0}건</p>
      </header>
      <CardList cards={result?.items ?? []} showTrack empty="이 주제의 최근 기사가 없습니다" />
      {result && result.total > result.size ? (
        <PaginationBar pathname="/topics" params={{ ...selected }} page={result.page} size={result.size} total={result.total} />
      ) : null}
    </div>
  ) : (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">주제 탐색</h1>
      <p className="text-sm text-muted-foreground">분야 15개 · 테마 75개 · DX 사업부 · 영향(기회/위험/관찰)으로 기사를 찾아보세요.</p>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {Object.entries(FIELD_LABEL).map(([key, label]) => (
          <Link key={key} href={`/topics?field=${key}`} className="flex items-center justify-between rounded-lg border p-3 hover:border-primary/40">
            <span className="font-medium">{label}</span>
            <span className="text-sm text-muted-foreground tabular-nums">{counts.fields[key] ?? 0}</span>
          </Link>
        ))}
      </div>
    </div>
  );
  return <ThreePane nav={<TaxonomyTree counts={counts} selected={selected} />} main={main} aside={<TopicAside counts={counts} />} mainLabel="기사" />;
}

function TopicAside({ counts }: { counts: Awaited<ReturnType<typeof reader.taxonomy>> }) {
  const top = Object.entries(counts.themes)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  return (
    <section className="space-y-3 rounded-xl border bg-card p-4">
      <h2 className="font-semibold">최근 {counts.window_days}일 많이 다룬 테마</h2>
      <ol className="space-y-1.5 text-sm">
        {top.map(([theme, count], index) => (
          <li key={theme} className="flex items-center gap-2">
            <span className="w-5 text-right text-muted-foreground tabular-nums">{index + 1}</span>
            <Link href={`/topics?theme=${theme}`} className="min-w-0 flex-1 truncate hover:underline">
              {THEME_LABEL[theme] ?? theme}
            </Link>
            <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
