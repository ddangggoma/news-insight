import { ExternalLink, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { ArtificialAnalysisCharts } from "@/components/reader/benchmarks/artificial-analysis";
import { DeepSweChart } from "@/components/reader/benchmarks/deepswe";
import { LiveBenchTable } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BENCHMARK_SITES,
  type BenchmarkSite,
  type BenchmarkSiteKey,
  SITE_BLURB,
  SITE_TITLE,
  boardLabel,
  newModels,
  openWeightsIndex,
} from "@/lib/benchmark-types";
import { formatDateTime } from "@/lib/format";

const anchor = (key: string) => `bench-${key}`;

function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{children}</div>;
}

function SiteCard({ siteKey, site, summary, openIndex }: { siteKey: BenchmarkSiteKey; site: BenchmarkSite | undefined; summary: BenchmarkSite | undefined; openIndex: Set<string> }) {
  // freshness from the summary the header uses; the full response is the same snapshot
  const meta = summary ?? site;
  const title = meta?.title ?? SITE_TITLE[siteKey];
  let body: ReactNode;
  if (!site) {
    body =
      siteKey === "artificial_analysis" ? (
        <Empty>
          <span className="block font-medium text-foreground">키 미설정</span>
          Artificial Analysis API 키가 설정되면 매일 03:30에 함께 수집합니다.
        </Empty>
      ) : (
        <Empty>아직 수집된 순위가 없습니다.</Empty>
      );
  } else if (siteKey === "deepswe") body = <DeepSweChart site={site} />;
  else if (siteKey === "livebench") body = <LiveBenchTable site={site} openIndex={openIndex} />;
  else if (siteKey === "lmarena") body = <LmArenaTable site={site} />;
  else body = <ArtificialAnalysisCharts site={site} />;

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
      <CardContent className="min-w-0">{body}</CardContent>
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
 * The AI 모델 tab: Opus's note on the day's leaderboard moves, models new to a board, then
 * one card per site recreating that site's own chart or table. `summary` is the light
 * all-sites response (top 10 per board); `sites` holds each site's full rows.
 */
export function ModelsTab({ summary, sites, note }: { summary: BenchmarkSite[]; sites: Partial<Record<BenchmarkSiteKey, BenchmarkSite>>; note: string }) {
  const bySite = new Map(summary.map((s) => [s.site, s]));
  const arrivals = newModels(summary);
  const openIndex = openWeightsIndex([sites.lmarena, sites.artificial_analysis]);

  return (
    <div className="space-y-5">
      {note && (
        <div className="rounded-lg border bg-muted/40 px-4 py-3">
          <p className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="size-3.5" aria-hidden />
            오늘의 순위 변화 (Opus)
          </p>
          <p className="text-sm leading-relaxed">{note}</p>
        </div>
      )}

      <nav aria-label="벤치마크 사이트" className="flex flex-wrap gap-2 text-xs">
        {BENCHMARK_SITES.map((key) => {
          const meta = bySite.get(key);
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
                  <span className="text-muted-foreground">{`${a.title}${bySite.get(a.site)!.boards.length > 1 ? ` ${boardLabel(a.site, a.board)}` : ""} ${a.rank}위`}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {BENCHMARK_SITES.map((key) => (
        <SiteCard key={key} siteKey={key} site={sites[key]} summary={bySite.get(key)} openIndex={openIndex} />
      ))}
    </div>
  );
}
