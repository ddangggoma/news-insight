import { ExternalLink, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { ArtificialAnalysisCharts } from "@/components/reader/benchmarks/artificial-analysis";
import { DeepSweChart } from "@/components/reader/benchmarks/deepswe";
import { LiveBenchTable } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { BENCHMARK_SITES, type BenchmarkSite, type BenchmarkSiteKey, SITE_BLURB, SITE_TITLE, boardLabel, newModels } from "@/lib/benchmark-types";
import { type BenchmarkViews, type SiteMeta, projectViews, siteMeta } from "@/lib/benchmark-view";
import { formatBriefingDate, formatDateTime } from "@/lib/format";

const anchor = (key: string) => `bench-${key}`;

function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{children}</div>;
}

function SiteBody({ siteKey, meta, views }: { siteKey: BenchmarkSiteKey; meta: SiteMeta; views: BenchmarkViews }) {
  if (siteKey === "deepswe" && views.deepswe) return <DeepSweChart view={views.deepswe} />;
  if (siteKey === "livebench" && views.livebench) return <LiveBenchTable models={views.livebench} />;
  if (siteKey === "lmarena" && views.lmarena) return <LmArenaTable view={views.lmarena} />;
  if (siteKey === "artificial_analysis" && views.artificial_analysis)
    return <ArtificialAnalysisCharts models={views.artificial_analysis} sourceUrl={meta.source_url} attribution={meta.attribution} />;
  return <Empty>아직 수집된 순위가 없습니다.</Empty>;
}

function SiteCard({ siteKey, meta, views }: { siteKey: BenchmarkSiteKey; meta: SiteMeta | undefined; views: BenchmarkViews }) {
  const title = meta?.title ?? SITE_TITLE[siteKey];
  return (
    <Card id={anchor(siteKey)} role="region" aria-label={title} className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base font-semibold">
          {title}
          {meta?.release && (
            <Badge variant="outline" className="font-normal text-muted-foreground">
              {`기준 ${meta.release}`}
            </Badge>
          )}
          {meta?.stale && (
            <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400" title="48시간 넘게 새로 수집하지 못했습니다">
              갱신 지연
            </Badge>
          )}
        </CardTitle>
        <CardDescription>{SITE_BLURB[siteKey]}</CardDescription>
      </CardHeader>
      <CardContent className="min-w-0">
        {meta ? (
          <SiteBody siteKey={siteKey} meta={meta} views={views} />
        ) : siteKey === "artificial_analysis" ? (
          <Empty>
            <span className="block font-medium text-foreground">키 미설정</span>
            Artificial Analysis API 키가 설정되면 매일 03:30에 함께 수집합니다.
          </Empty>
        ) : (
          <Empty>아직 수집된 순위가 없습니다.</Empty>
        )}
      </CardContent>
      {meta && (
        <CardFooter className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t py-3 text-xs text-muted-foreground">
          <span>{`갱신 ${formatDateTime(meta.fetched_at)}`}</span>
          <a href={meta.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-foreground hover:underline">
            원본 보기
            <ExternalLink className="size-3" aria-hidden />
          </a>
          <span>{meta.license}</span>
          {siteKey !== "artificial_analysis" && <span>{`출처: ${meta.attribution}`}</span>}
        </CardFooter>
      )}
    </Card>
  );
}

/**
 * The AI 모델 tab: Opus's note on the leaderboard moves, models new to a board, then one card
 * per site recreating that site's own chart or table. A server component: `sites` (each
 * site's full rows) is projected here, and only the projections reach the client cards.
 * `summary` (top 10 per board) feeds the arrivals; without it the tab still works.
 * `noteDate` is the day the reader picked (null = latest): the note belongs to that day,
 * while the leaderboards below are always the latest.
 */
export function ModelsTab({
  summary,
  sites,
  note,
  noteDate = null,
}: {
  summary: BenchmarkSite[] | null;
  sites: Partial<Record<BenchmarkSiteKey, BenchmarkSite>>;
  note: string;
  noteDate?: string | null;
}) {
  const views = projectViews(sites);
  const metas = new Map<string, SiteMeta>();
  for (const site of summary ?? []) metas.set(site.site, siteMeta(site));
  for (const key of BENCHMARK_SITES) {
    const site = sites[key];
    // freshness from the summary the header uses when there is one (same snapshot)
    if (site && !metas.has(key)) metas.set(key, siteMeta(site));
  }
  const arrivals = summary ? newModels(summary) : [];

  return (
    <div className="space-y-5">
      {note && (
        <div className="rounded-lg border bg-muted/40 px-4 py-3">
          <p className="mb-1 flex flex-wrap items-center gap-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="size-3.5" aria-hidden />
            {noteDate ? `${formatBriefingDate(noteDate)}의 순위 변화 (Opus) · 아래 순위표는 최신 기준` : "오늘의 순위 변화 (Opus)"}
          </p>
          <p className="text-sm leading-relaxed">{note}</p>
        </div>
      )}

      <nav aria-label="벤치마크 사이트" className="flex flex-wrap gap-2 text-xs">
        {BENCHMARK_SITES.map((key) => {
          const meta = metas.get(key);
          return (
            <a key={key} href={`#${anchor(key)}`} className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 hover:bg-muted">
              <span className="font-medium">{meta?.title ?? SITE_TITLE[key]}</span>
              <span className={meta?.stale ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}>
                {!meta ? (key === "artificial_analysis" ? "키 미설정" : "미수집") : meta.stale ? "갱신 지연" : formatDateTime(meta.fetched_at)}
              </span>
            </a>
          );
        })}
      </nav>

      {arrivals.length > 0 && (
        <div className="space-y-1.5">
          <h2 className="text-xs font-medium text-muted-foreground">새로 등장한 모델</h2>
          <ul aria-label="새로 등장한 모델" className="flex flex-wrap gap-1.5">
            {arrivals.map((a) => (
              <li key={`${a.site}|${a.board}|${a.model}`}>
                <a href={`#${anchor(a.site)}`} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs hover:bg-primary/15">
                  <span className="font-bold text-primary">NEW</span>
                  <span className="font-medium">{a.model}</span>
                  <span className="text-muted-foreground">{`${a.title}${(metas.get(a.site)?.boards.length ?? 0) > 1 ? ` ${boardLabel(a.site, a.board)}` : ""} ${a.rank}위`}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {BENCHMARK_SITES.map((key) => (
        <SiteCard key={key} siteKey={key} meta={metas.get(key)} views={views} />
      ))}
    </div>
  );
}
