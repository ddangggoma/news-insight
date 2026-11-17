import { ExternalLink, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { AppLink as Link } from "@/components/app-link";
import { EpochCard } from "@/components/reader/benchmarks/epoch";
import { ForecastBenchTable } from "@/components/reader/benchmarks/forecastbench";
import { LiveBenchTable } from "@/components/reader/benchmarks/livebench";
import { LmArenaTable } from "@/components/reader/benchmarks/lmarena";
import { OsWorldTable } from "@/components/reader/benchmarks/osworld";
import { SealCard } from "@/components/reader/benchmarks/seal";
import { SimpleBenchTable } from "@/components/reader/benchmarks/simplebench";
import { Tau2Table } from "@/components/reader/benchmarks/tau2";
import { TerminalBenchCard } from "@/components/reader/benchmarks/terminal-bench";
import { ValsCard } from "@/components/reader/benchmarks/vals";
import { VendingBenchCard } from "@/components/reader/benchmarks/vending-bench";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { BENCHMARK_GROUPS, type BenchmarkSite, type BenchmarkSiteKey, SITE_BLURB, SITE_TITLE, benchmarkHref, boardLabel, isSiteKey, newModels } from "@/lib/benchmark-types";
import { type BenchmarkViews, type SiteMeta, projectViews, siteMeta } from "@/lib/benchmark-view";
import { formatBriefingDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">{children}</div>;
}

function SiteBody({ siteKey, meta, views }: { siteKey: BenchmarkSiteKey; meta: SiteMeta; views: BenchmarkViews }) {
  const updated = (board: string) => meta.updated?.[board] ?? meta.release ?? null;
  if (siteKey === "livebench" && views.livebench) return <LiveBenchTable models={views.livebench} />;
  if (siteKey === "lmarena" && views.lmarena) return <LmArenaTable view={views.lmarena} />;
  if (siteKey === "terminal_bench" && views.terminal_bench) return <TerminalBenchCard view={views.terminal_bench} />;
  if (siteKey === "osworld" && views.osworld) return <OsWorldTable rows={views.osworld} updated={updated("main")} />;
  if (siteKey === "tau2" && views.tau2) return <Tau2Table view={views.tau2} />;
  if (siteKey === "epoch" && views.epoch) return <EpochCard boards={views.epoch} />;
  if (siteKey === "seal" && views.seal) return <SealCard boards={views.seal} />;
  if (siteKey === "vals" && views.vals) return <ValsCard rows={views.vals} updated={updated("vals_index")} />;
  if (siteKey === "vending_bench" && views.vending_bench) return <VendingBenchCard rows={views.vending_bench} updated={updated("main")} />;
  if (siteKey === "simplebench" && views.simplebench) return <SimpleBenchTable rows={views.simplebench} updated={updated("mcq")} />;
  if (siteKey === "forecastbench" && views.forecastbench) return <ForecastBenchTable rows={views.forecastbench} updated={updated("tournament")} />;
  return <Empty>아직 수집된 순위가 없습니다.</Empty>;
}

function SiteCard({ siteKey, meta, views }: { siteKey: BenchmarkSiteKey; meta: SiteMeta | undefined; views: BenchmarkViews }) {
  const title = meta?.title ?? SITE_TITLE[siteKey];
  return (
    <Card id={`bench-${siteKey}`} role="region" aria-label={title} className="scroll-mt-20">
      <CardHeader>
        <CardTitle role="heading" aria-level={3} className="flex flex-wrap items-center gap-2 text-base font-semibold">
          {title}
          {/* one board: its date here; several (LMArena, Epoch, SEAL boards): each board shows its own */}
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
      <CardContent className="min-w-0">{meta ? <SiteBody siteKey={siteKey} meta={meta} views={views} /> : <Empty>아직 수집된 순위가 없습니다.</Empty>}</CardContent>
      {meta && (
        <CardFooter className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t py-3 text-xs text-muted-foreground">
          <span>{`갱신 ${formatDateTime(meta.fetched_at)}`}</span>
          <a href={meta.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-foreground hover:underline">
            원본 보기
            <ExternalLink className="size-3" aria-hidden />
          </a>
          <span>{`라이선스: ${meta.license}`}</span>
          <span>{`출처: ${meta.attribution}`}</span>
        </CardFooter>
      )}
    </Card>
  );
}

/** The id of the section: `/spotlight?tab=benchmarks#benchmarks` and in-page links land on it. */
export const BENCHMARKS_ANCHOR = "benchmarks";

/**
 * The 벤치마크 tab of 주목 받는: Opus's note on the leaderboard moves, the models new to a board,
 * a menu of the sites in two groups (AI 에이전트 / AI 모델) and, under it, the one site picked
 * there (`?tab=benchmarks&site=<key>`; the first site when none is named), recreating that
 * site's own default chart or table. A server component: `full` (the picked site's full rows,
 * the only site whose rows are fetched) is projected here, and only the projection reaches the
 * client card. `summary` (top 10 per board of every site) feeds the menu's freshness and the
 * arrivals; without it the tab still works, and when `full` is missing the card falls back to
 * the summary's rows. `date` is the day the reader picked (null = latest): the note belongs to
 * that day, while the leaderboards are always the latest.
 */
export function BenchmarksSection({
  summary,
  site,
  full,
  note,
  date = null,
  noteDate = null,
}: {
  summary: BenchmarkSite[] | null;
  site: BenchmarkSiteKey;
  full: BenchmarkSite | null;
  note: string;
  /** Kept in the menu's links so the picked day (and its note) stays. */
  date?: string | null;
  noteDate?: string | null;
}) {
  const metas = new Map<string, SiteMeta>();
  for (const one of summary ?? []) metas.set(one.site, siteMeta(one));
  const picked = full ?? summary?.find((one) => one.site === site) ?? null;
  // freshness from the summary the menu uses when there is one (same snapshot)
  if (picked && !metas.has(site)) metas.set(site, siteMeta(picked));
  const views = projectViews(picked ? { [site]: picked } : {});
  const arrivals = summary ? newModels(summary) : [];

  return (
    <section id={BENCHMARKS_ANCHOR} aria-labelledby={`${BENCHMARKS_ANCHOR}-title`} className="scroll-mt-20 space-y-5">
      <div className="space-y-1">
        <h2 id={`${BENCHMARKS_ANCHOR}-title`} className="text-lg font-semibold">
          AI 벤치마크
        </h2>
        <p className="text-sm text-muted-foreground">
          각 사이트의 순위를 그 사이트가 처음 열 때 보여 주는 기준(행·순위·점수 열·필터) 그대로 옮겼습니다. 아래에서 사이트를 고르면 그 사이트의 순위표를 봅니다.
        </p>
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

      {arrivals.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-sm font-medium text-muted-foreground">새로 등장한 모델</h3>
          <ul aria-label="새로 등장한 모델" className="flex flex-wrap gap-1.5">
            {arrivals.map((a) => (
              <li key={`${a.site}|${a.board}|${a.model}`}>
                <Link
                  href={isSiteKey(a.site) ? benchmarkHref(a.site, date) : benchmarkHref(null, date)}
                  scroll={false}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs hover:bg-primary/15"
                >
                  <span className="font-bold text-primary">NEW</span>
                  <span className="font-medium">{a.model}</span>
                  <span className="text-muted-foreground">{`${a.title}${(metas.get(a.site)?.boards.length ?? 0) > 1 ? ` ${boardLabel(a.site, a.board)}` : ""} ${a.rank}위`}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <nav aria-label="벤치마크 사이트" className="space-y-2 rounded-lg border bg-muted/30 px-3 py-3">
        {BENCHMARK_GROUPS.map((group) => (
          <div key={group.key} role="group" aria-label={group.title} className="flex flex-wrap items-center gap-1.5">
            <span className="w-full text-xs font-semibold text-muted-foreground sm:w-24" title={group.blurb}>
              {group.title}
            </span>
            {group.sites.map((key) => {
              const meta = metas.get(key);
              const active = key === site;
              const state = !meta ? "미수집" : meta.stale ? "갱신 지연" : null;
              return (
                <Link
                  key={key}
                  href={benchmarkHref(key, date)}
                  scroll={false}
                  aria-current={active ? "page" : undefined}
                  title={meta ? `갱신 ${formatDateTime(meta.fetched_at)}` : undefined}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm whitespace-nowrap transition-colors",
                    active ? "border-primary bg-primary/10 font-semibold text-primary" : "bg-background text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {meta?.title ?? SITE_TITLE[key]}
                  {state && <span className={cn("text-xs font-normal", meta?.stale ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>{state}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <SiteCard key={site} siteKey={site} meta={metas.get(site)} views={views} />
    </section>
  );
}
