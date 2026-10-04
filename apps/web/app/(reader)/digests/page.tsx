import { Rss } from "lucide-react";
import Link from "next/link";

import { formatNumber } from "@/lib/format";
import { pageParam, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { DigestSummary, Page } from "@/lib/types";

export const metadata = { title: "다이제스트" };

export default async function DigestsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const page = pageParam(await searchParams);
  const digests = await readerGet<Page<DigestSummary>>("/digests", { page, size: 30 }, REVALIDATE.digest);
  const pages = Math.max(1, Math.ceil(digests.total / digests.size));
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-8 md:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">데일리 다이제스트</h1>
          <p className="mt-1 text-sm text-muted-foreground">매일 05:00 KST, 전날 수집한 기사를 근거로 쓴 요약입니다.</p>
        </div>
        <a href="/feed.xml" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
          <Rss className="size-4" aria-hidden /> RSS 구독
        </a>
      </header>
      {digests.items.length ? (
        <ol className="divide-y border-y">
          {digests.items.map((digest) => (
            <li key={`${digest.digest_date}-${digest.version}`}>
              <Link href={`/digests/${digest.digest_date}`} className="block py-4 hover:bg-muted/50">
                <span className="text-xs text-muted-foreground tabular-nums">
                  {digest.digest_date} · 기사 {formatNumber(digest.item_count)}건
                </span>
                <span className="mt-1 block text-base leading-snug font-semibold">{digest.headline}</span>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <p className="py-16 text-center text-muted-foreground">아직 발행된 다이제스트가 없습니다.</p>
      )}
      {pages > 1 ? (
        <nav aria-label="페이지" className="flex justify-center gap-4 text-sm">
          {page > 1 ? <Link href={`/digests?page=${page - 1}`}>← 최근</Link> : null}
          <span className="text-muted-foreground tabular-nums">
            {page} / {pages}
          </span>
          {page < pages ? <Link href={`/digests?page=${page + 1}`}>이전 →</Link> : null}
        </nav>
      ) : null}
    </main>
  );
}
