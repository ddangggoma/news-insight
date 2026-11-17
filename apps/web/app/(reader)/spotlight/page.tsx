import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { BenchmarksSection } from "@/components/reader/benchmarks/benchmarks-section";
import { BenchmarksHashRedirect } from "@/components/reader/benchmarks/hash-redirect";
import { SpotlightBrowser } from "@/components/reader/spotlight/browser";
import { DateSelect } from "@/components/reader/spotlight/date-select";
import { GeneratingBand } from "@/components/reader/spotlight/generating-band";
import { SpotlightTabs } from "@/components/reader/spotlight/spotlight-tabs";
import { ApiError } from "@/lib/api";
import { type BenchmarkSite, type BenchmarkSiteKey, parseSite } from "@/lib/benchmark-types";
import { formatDateTime } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";
import { BENCHMARKS_TAB, RETIRED_MODELS_TAB, SECTION_LABEL, type SpotlightView, isCalendarDay, parseFilters, parseTab, spotlightHref } from "@/lib/spotlight-types";

/**
 * The 벤치마크 tab's data: the all-sites summary (the menu's freshness, today's arrivals) and the
 * full rows of the one site picked in the menu, fetched side by side; the other sites' rows are
 * never asked for. A failed summary only hides the arrivals; when the site's full request fails
 * BenchmarksSection falls back to its summary rows (top 10 per board). The rows stay on the
 * server: BenchmarksSection projects them before any client card.
 */
async function loadBenchmarks(site: BenchmarkSiteKey): Promise<{ summary: BenchmarkSite[] | null; full: BenchmarkSite | null }> {
  const [summary, full] = await Promise.all([
    readerGet<BenchmarkSite[]>("/benchmarks", {}, REVALIDATE.benchmarks).catch(() => null),
    readerGet<BenchmarkSite[]>("/benchmarks", { site }, REVALIDATE.benchmarks).then(
      (rows) => rows[0] ?? null,
      () => null,
    ),
  ]);
  return { summary, full };
}

export const metadata: Metadata = { title: "주목 받는", robots: { index: false } };

export default async function SpotlightPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const tab = parseTab(param(sp, "tab"));
  const requested = param(sp, "date");
  const filters = parseFilters(param(sp, "field"), param(sp, "group"));
  if (requested !== undefined && !isCalendarDay(requested)) notFound();
  // the former 「AI 모델」 tab: its leaderboards are the 벤치마크 tab now
  if (param(sp, "tab") === RETIRED_MODELS_TAB) redirect(spotlightHref(BENCHMARKS_TAB, requested ?? null));

  let view: SpotlightView;
  try {
    view = await readerGet<SpotlightView>("/spotlight", requested ? { date: requested } : {}, REVALIDATE.spotlight);
  } catch (error) {
    // a day that was never published, or one the API refuses as a date at all
    if (requested && error instanceof ApiError && [400, 404, 422].includes(error.status)) notFound();
    throw error;
  }

  // 벤치마크: one site at a time (`?site=`, the menu's first site when none is named)
  const site = parseSite(param(sp, "site"));
  const benchmarks = tab === BENCHMARKS_TAB ? await loadBenchmarks(site) : null;

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <h1 className="text-xl font-semibold">주목 받는</h1>
          <p className="text-sm text-muted-foreground">
            뉴스·제품·AI 모델·서비스·오픈소스·인터뷰·커뮤니티·연구·특허별로 최근 24시간 Top 10과 지난 7일 동안 이어진 지속 주목 Top 5를 모았습니다. AI 리더보드는 벤치마크 탭에서
            사이트별로 봅니다.
            {view.generated_at && ` ${formatDateTime(view.generated_at)} 생성.`}
          </p>
        </div>
        <DateSelect dates={view.available_dates} current={view.date} tab={tab} />
      </div>

      {view.generating && <GeneratingBand />}

      <SpotlightTabs active={tab} date={requested ?? null} />

      {tab === "overview" ? (
        <SpotlightBrowser view={view} tab={tab} date={requested ?? null} initial={filters} />
      ) : tab === BENCHMARKS_TAB ? (
        <BenchmarksSection
          summary={benchmarks?.summary ?? null}
          site={site}
          full={benchmarks?.full ?? null}
          note={view.benchmark_note}
          date={requested ?? null}
          noteDate={requested && requested !== view.available_dates[0] ? requested : null}
        />
      ) : (
        <section aria-label={SECTION_LABEL[tab]}>
          <SpotlightBrowser key={tab} view={view} tab={tab} date={requested ?? null} initial={filters} />
          {/* links from when the leaderboards sat under this tab (`?tab=ai#benchmarks`) */}
          {tab === "ai" && <BenchmarksHashRedirect date={requested ?? null} />}
        </section>
      )}
    </main>
  );
}
