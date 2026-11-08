import { ExternalLink, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { ArtificialAnalysisCharts } from "@/components/reader/benchmarks/artificial-analysis";
import { DeepSweChart } from "@/components/reader/benchmarks/deepswe";
import { EpochCard } from "@/components/reader/benchmarks/epoch";
import { LiveBenchTable } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { OsWorldTable } from "@/components/reader/benchmarks/osworld";
import { Tau2Table } from "@/components/reader/benchmarks/tau2";
import { TerminalBenchCard } from "@/components/reader/benchmarks/terminal-bench";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { BENCHMARK_GROUPS, BENCHMARK_SITES, type BenchmarkSite, type BenchmarkSiteKey, SITE_BLURB, SITE_TITLE, boardLabel, newModels } from "@/lib/benchmark-types";
import { type BenchmarkViews, type SiteMeta, projectViews, siteMeta } from "@/lib/benchmark-view";
import { formatBriefingDate, formatDateTime } from "@/lib/format";

const anchor = (key: string) => `bench-${key}`;
const groupAnchor = (key: string) => `bench-group-${key}`;

function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{children}</div>;
}

function SiteBody({ siteKey, meta, views }: { siteKey: BenchmarkSiteKey; meta: SiteMeta; views: BenchmarkViews }) {
  if (siteKey === "deepswe" && views.deepswe) return <DeepSweChart view={views.deepswe} />;
  if (siteKey === "livebench" && views.livebench) return <LiveBenchTable models={views.livebench} />;
  if (siteKey === "lmarena" && views.lmarena) return <LmArenaTable view={views.lmarena} />;
  if (siteKey === "terminal_bench" && views.terminal_bench) return <TerminalBenchCard view={views.terminal_bench} />;
  if (siteKey === "osworld" && views.osworld) return <OsWorldTable rows={views.osworld} updated={meta.updated?.main ?? meta.release ?? null} />;
  if (siteKey === "tau2" && views.tau2) return <Tau2Table view={views.tau2} />;
  if (siteKey === "epoch" && views.epoch) return <EpochCard boards={views.epoch} />;
  if (siteKey === "artificial_analysis" && views.artificial_analysis)
    return <ArtificialAnalysisCharts models={views.artificial_analysis} sourceUrl={meta.source_url} attribution={meta.attribution} />;
  return <Empty>아직 수집된 순위가 없습니다.</Empty>;
}

function SiteCard({ siteKey, meta, views }: { siteKey: BenchmarkSiteKey; meta: SiteMeta | undefined; views: BenchmarkViews }) {
  const title = meta?.title ?? SITE_TITLE[siteKey];
  return (
    <Card id={anchor(siteKey)} role="region" aria-label={title} className="scroll-mt-20">
      <CardHeader>
        <CardTitle role="heading" aria-level={4} className="flex flex-wrap items-center gap-2 text-base font-semibold">
          {title}
          {/* one board: its date here; several (DeepSWE versions, LMArena boards): each board shows its own */}
          {meta?.release && Object.keys(meta.updated ?? {}).length <= 1 && (
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

/** The anchor of the benchmarks inside 「AI 모델·서비스」 (old `?tab=models` links land on it). */
export const BENCHMARKS_ANCHOR = "benchmarks";

/**
 * 「AI 모델 벤치마크」 under the AI 모델·서비스 tab's ranked list: Opus's note on the leaderboard
 * moves, models new to a board, then one card per site recreating that site's own chart or
 * table. A server component: `sites` (each site's full rows) is projected here, and only the
 * projections reach the client cards. `summary` (top 10 per board) feeds the arrivals; without
 * it the section still works. `noteDate` is the day the reader picked (null = latest): the note
 * belongs to that day, while the leaderboards below are always the latest.
 */
export function BenchmarksSection({
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
    <section id={BENCHMARKS_ANCHOR} aria-labelledby={`${BENCHMARKS_ANCHOR}-title`} className="scroll-mt-20 space-y-5 border-t pt-6">
      <div className="space-y-1">
        <h2 id={`${BENCHMARKS_ANCHOR}-title`} className="text-lg font-semibold">
          AI 모델 벤치마크
        </h2>
        <p className="text-sm text-muted-foreground">각 사이트의 순위를 그 사이트가 처음 열 때 보여 주는 기준(행·순위·점수 열·필터) 그대로 옮겼습니다.</p>
      </div>
      {note && (
        <div className="rounded-lg border bg-muted/40 px-4 py-3">
          <p className="mb-1 flex flex-wrap items-center gap-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="size-3.5" aria-hidden />
            {noteDate ? `${formatBriefingDate(noteDate)}의 순위 변화 (Opus) · 아래 순위표는 최신 기준` : "오늘의 순위 변화 (Opus)"}
          </p>
          <p className="text-sm leading-relaxed">{note}</p>
        </div>
      )}

      <nav aria-label="벤치마크 사이트" className="space-y-1.5 text-xs">
        {BENCHMARK_GROUPS.map((group) => (
          <div key={group.key} className="flex flex-wrap items-center gap-2">
            <a href={`#${groupAnchor(group.key)}`} className="w-full text-xs font-semibold text-muted-foreground hover:text-foreground hover:underline sm:w-auto">
              {group.title}
            </a>
            {group.sites.map((key) => {
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
          </div>
        ))}
      </nav>

      {arrivals.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-sm font-medium text-muted-foreground">새로 등장한 모델</h3>
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

      {BENCHMARK_GROUPS.map((group) => (
        <div key={group.key} id={groupAnchor(group.key)} role="group" aria-labelledby={`${groupAnchor(group.key)}-title`} className="scroll-mt-20 space-y-4">
          <div className="space-y-0.5 pt-2">
            <h3 id={`${groupAnchor(group.key)}-title`} className="text-base font-semibold">
              {group.title}
            </h3>
            <p className="text-sm text-muted-foreground">{group.blurb}</p>
          </div>
          {group.sites.map((key) => (
            <SiteCard key={key} siteKey={key} meta={metas.get(key)} views={views} />
          ))}
        </div>
      ))}
    </section>
  );
}
