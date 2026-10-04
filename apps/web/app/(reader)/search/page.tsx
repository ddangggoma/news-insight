import type { Metadata } from "next";
import Link from "next/link";

import { PaginationBar } from "@/components/console/pagination-bar";
import { CardList } from "@/components/reader/card-list";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TRACK_LABEL } from "@/lib/format";
import { pageParam, param, type SearchParams } from "@/lib/params";
import { reader } from "@/lib/reader";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "검색" };
export const dynamic = "force-dynamic";

export default async function SearchPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const q = param(params, "q")?.slice(0, 100);
  const track = param(params, "track");
  const page = pageParam(params);
  const result = q ? await reader.cards({ q, track, page, size: 30 }) : null;
  return (
    <main className="mx-auto w-full max-w-4xl space-y-6 px-4 py-8">
      <form action="/search" role="search" className="flex gap-2">
        <label htmlFor="q" className="sr-only">
          검색어
        </label>
        <Input id="q" name="q" type="search" defaultValue={q} placeholder="원문 제목·한국어 제목·키워드" autoFocus className="h-10" />
        {track ? <input type="hidden" name="track" value={track} /> : null}
        <Button type="submit" className="h-10">
          검색
        </Button>
      </form>
      {q ? (
        <>
          <div className="flex flex-wrap gap-1.5" aria-label="트랙 필터">
            {[undefined, ...Object.keys(TRACK_LABEL)].map((key) => (
              <Link
                key={key ?? "all"}
                href={`/search?q=${encodeURIComponent(q)}${key ? `&track=${key}` : ""}`}
                aria-current={track === key ? "page" : undefined}
                className={cn("rounded-full border px-3 py-1 text-sm hover:bg-muted", track === key && "border-primary bg-primary/10 text-primary")}
              >
                {key ? TRACK_LABEL[key as keyof typeof TRACK_LABEL] : "전체"}
              </Link>
            ))}
          </div>
          <h1 className="text-lg font-semibold">
            ‘{q}’ 검색 결과 <span className="text-muted-foreground">{result?.total ?? 0}건</span>
          </h1>
          <CardList cards={result?.items ?? []} showTrack empty="검색 결과가 없습니다" />
          {result && result.total > result.size ? (
            <PaginationBar pathname="/search" params={{ q, track }} page={result.page} size={result.size} total={result.total} />
          ) : null}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">원문 제목, 한국어 제목, 키워드에서 찾습니다. 같은 이슈의 중복 기사는 대표 기사 하나로 묶어 보여 줍니다.</p>
      )}
    </main>
  );
}
