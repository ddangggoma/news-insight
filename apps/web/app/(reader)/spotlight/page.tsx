import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ModelsTab } from "@/components/reader/benchmarks/models-tab";
import { DateSelect } from "@/components/reader/spotlight/date-select";
import { GeneratingBand } from "@/components/reader/spotlight/generating-band";
import { Overview } from "@/components/reader/spotlight/overview";
import { SectionList } from "@/components/reader/spotlight/section-list";
import { SpotlightTabs } from "@/components/reader/spotlight/spotlight-tabs";
import { ApiError } from "@/lib/api";
import { BENCHMARK_SITES, type BenchmarkSite, type BenchmarkSiteKey, forClient } from "@/lib/benchmark-types";
import { formatDateTime } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";
import { SECTION_LABEL, type SpotlightView, isCalendarDay, parseTab } from "@/lib/spotlight-types";

/**
 * The AI 모델 tab's data: the all-sites summary (freshness, today's arrivals) and each site's
 * full rows, fetched side by side so every cached response stays small. A site whose full
 * request fails falls back to its summary rows (top 10 per board).
 */
async function loadBenchmarks(): Promise<{ summary: BenchmarkSite[]; sites: Partial<Record<BenchmarkSiteKey, BenchmarkSite>> }> {
  const [summary, ...full] = await Promise.all([
    readerGet<BenchmarkSite[]>("/benchmarks", {}, REVALIDATE.benchmarks),
    ...BENCHMARK_SITES.map((site) =>
      readerGet<BenchmarkSite[]>("/benchmarks", { site }, REVALIDATE.benchmarks).then(
        (rows) => rows[0] ?? null,
        () => null,
      ),
    ),
  ]);
  const sites: Partial<Record<BenchmarkSiteKey, BenchmarkSite>> = {};
  BENCHMARK_SITES.forEach((key, index) => {
    const site = full[index] ?? summary.find((s) => s.site === key);
    if (site) sites[key] = forClient(site);
  });
  return { summary, sites };
}

export const metadata: Metadata = { title: "주목 받는", robots: { index: false } };

export default async function SpotlightPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const tab = parseTab(param(sp, "tab"));
  const requested = param(sp, "date");
  if (requested !== undefined && !isCalendarDay(requested)) notFound();

  let view: SpotlightView;
  try {
    view = await readerGet<SpotlightView>("/spotlight", requested ? { date: requested } : {}, REVALIDATE.spotlight);
  } catch (error) {
    // a day that was never published, or one the API refuses as a date at all
    if (requested && error instanceof ApiError && [400, 404, 422].includes(error.status)) notFound();
    throw error;
  }

  const benchmarks = tab === "models" ? await loadBenchmarks() : null;

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <h1 className="text-xl font-semibold">주목 받는</h1>
          <p className="text-sm text-muted-foreground">
            하루 동안 가장 화제가 된 뉴스·제품·오픈소스·인터뷰·커뮤니티·연구·특허를 분야별 Top 10으로 모았습니다.
            {view.generated_at && ` ${formatDateTime(view.generated_at)} 생성.`}
          </p>
        </div>
        <DateSelect dates={view.available_dates} current={view.date} tab={tab} />
      </div>

      {view.generating && <GeneratingBand />}

      <SpotlightTabs active={tab} date={requested ?? null} />

      {tab === "overview" ? (
        <Overview view={view} date={requested ?? null} />
      ) : tab === "models" ? (
        <section aria-label="AI 모델">
          {benchmarks && <ModelsTab summary={benchmarks.summary} sites={benchmarks.sites} note={view.benchmark_note} />}
        </section>
      ) : (
        <section aria-label={SECTION_LABEL[tab]}>
          <SectionList entries={view.sections[tab]} />
        </section>
      )}
    </main>
  );
}
