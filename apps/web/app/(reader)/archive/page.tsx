import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/console/empty-state";
import { PaginationBar } from "@/components/console/pagination-bar";
import { formatBriefingDate } from "@/lib/format";
import { pageParam, type SearchParams } from "@/lib/params";
import { reader } from "@/lib/reader";

export const metadata: Metadata = { title: "아카이브" };
export const dynamic = "force-dynamic";

export default async function ArchivePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const page = pageParam(await searchParams);
  const archive = await reader.archive(page);
  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">아카이브</h1>
        <p className="text-sm text-muted-foreground">품질 게이트를 통과해 발행된 데일리 브리핑입니다.</p>
      </header>
      {archive && archive.items.length > 0 ? (
        <>
          <ol className="divide-y rounded-xl border">
            {archive.items.map((entry) => (
              <li key={entry.briefing_date}>
                <Link href={`/briefings/${entry.briefing_date}`} className="flex flex-col gap-1 p-4 hover:bg-muted/50 sm:flex-row sm:items-baseline sm:gap-4">
                  <time dateTime={entry.briefing_date} className="shrink-0 text-sm font-medium text-muted-foreground sm:w-44">
                    {formatBriefingDate(entry.briefing_date)}
                  </time>
                  <span className="min-w-0 flex-1 font-medium">{entry.headline ?? "데일리 브리핑"}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{entry.items}건</span>
                </Link>
              </li>
            ))}
          </ol>
          <PaginationBar pathname="/archive" params={{}} page={archive.page} size={archive.size} total={archive.total} />
        </>
      ) : (
        <EmptyState title="아직 발행된 브리핑이 없습니다" description="매일 05:00 KST에 품질 게이트를 통과한 브리핑만 발행됩니다." />
      )}
    </main>
  );
}
