import Link from "next/link";

import { ActiveFilters } from "@/components/reader/active-filters";
import { DigestBanner } from "@/components/reader/digest-banner";
import { FacetPanel } from "@/components/reader/facet-panel";
import { FacetSheet } from "@/components/reader/facet-sheet";
import { FeedInsightSwitch } from "@/components/reader/feed-insight-switch";
import { FeedToolbar } from "@/components/reader/feed-toolbar";
import { InsightPanel } from "@/components/reader/insight-panel";
import { StoryRow } from "@/components/reader/story-row";
import { ApiError } from "@/lib/api";
import type { SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { activeChips, apiParams, pageHref, parseReaderFilters } from "@/lib/reader-filters";
import type { Facets, FeedPage, Insights, PublicDigest } from "@/lib/reader-types";

export const metadata = { title: { absolute: "DX 인텔리전스 — 기술·사업부별 IT 뉴스 탐색" } };

/** The banner is optional: without a digest, or if it fails to load, the feed still renders. */
async function latestDigest(): Promise<PublicDigest | null> {
  try {
    return await readerGet<PublicDigest>("/digests/latest", {}, REVALIDATE.digest);
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) console.error("latest digest failed", error);
    return null;
  }
}

export default async function ExplorePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const filters = parseReaderFilters(await searchParams);
  const params = apiParams(filters);
  const { page: _page, sort: _sort, ...aggregate } = params;
  const [feed, facets, insights, digest] = await Promise.all([
    readerGet<FeedPage>("/items", params),
    readerGet<Facets>("/facets", aggregate),
    readerGet<Insights>("/insights", aggregate),
    latestDigest(),
  ]);
  const pages = Math.max(1, Math.ceil(feed.total / feed.size));
  const companyNames = Object.fromEntries(feed.items.flatMap((item) => (item.companies ?? []).map((c) => [c.key, c.label])));

  const feedColumn = (
    <section aria-label="기사 목록" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <FacetSheet facets={facets} filters={filters} active={activeChips(filters).length} />
        <ActiveFilters filters={filters} companies={companyNames} />
      </div>
      <FeedToolbar filters={filters} total={feed.total} itemsTotal={feed.items_total} />
      {feed.items.length ? (
        <div>
          {feed.items.map((item) => (
            <StoryRow key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <div className="py-16 text-center">
          <p className="font-semibold">조건에 맞는 기사가 없습니다</p>
          <p className="mt-1 text-sm text-muted-foreground">기간을 넓히거나 필터를 하나 지워 보세요.</p>
        </div>
      )}
      {pages > 1 ? (
        <nav aria-label="페이지" className="flex items-center justify-center gap-4 pt-2 text-sm">
          {filters.page > 1 ? <Link href={pageHref(filters, filters.page - 1)}>← 이전</Link> : <span className="text-muted-foreground">← 이전</span>}
          <span className="tabular-nums text-muted-foreground">
            {filters.page} / {pages}
          </span>
          {filters.page < pages ? <Link href={pageHref(filters, filters.page + 1)}>다음 →</Link> : <span className="text-muted-foreground">다음 →</span>}
        </nav>
      ) : null}
    </section>
  );

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-5 md:px-6">
      <h1 className="sr-only">기술 분야·DX 사업부별 IT 뉴스 탐색</h1>
      {digest ? (
        <div className="mb-5">
          <DigestBanner
            date={digest.digest_date}
            headline={digest.content.headline}
            insights={digest.content.insights.map((insight) => insight.title)}
          />
        </div>
      ) : null}
      <div className="grid gap-x-8 gap-y-4 md:grid-cols-[minmax(0,1fr)_280px] xl:grid-cols-[240px_minmax(0,1fr)_300px]">
        <aside aria-label="필터" className="hidden xl:block">
          <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto pr-1">
            <FacetPanel facets={facets} filters={filters} />
          </div>
        </aside>
        <FeedInsightSwitch
          feed={feedColumn}
          insight={
            <aside aria-label="인사이트" className="md:sticky md:top-20">
              <InsightPanel insights={insights} filters={filters} />
            </aside>
          }
        />
      </div>
    </main>
  );
}
