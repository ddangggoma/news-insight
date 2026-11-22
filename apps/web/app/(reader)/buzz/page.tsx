import type { Metadata } from "next";

import { BuzzList } from "@/components/reader/buzz/buzz-list";
import type { BuzzView } from "@/lib/buzz-types";
import { formatDateTime } from "@/lib/format";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "화제·속보", robots: { index: false } };

/**
 * Community buzz as signals (2026-11-19): what several communities are talking about at once, and
 * what they had before any news did. Community posts appear here inside their cluster only, never
 * in the news lists.
 */
export default async function BuzzPage() {
  await requireUser();
  const view = await readerGet<BuzzView>("/buzz", {}, REVALIDATE.buzz);
  const breaking = view.clusters.filter((cluster) => cluster.breaking).length;
  return (
    <main className="mx-auto max-w-3xl px-4 py-6 md:px-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">커뮤니티 화제·속보</h1>
        <p className="text-sm text-muted-foreground">
          {`최근 ${view.hours}시간, 여러 커뮤니티에서 함께 이야기되는 묶음 ${view.clusters.length}개`}
          {breaking ? ` · 뉴스보다 먼저 나온 속보 ${breaking}개` : ""}
          {` · ${formatDateTime(view.generated_at)} 기준`}
        </p>
        <p className="text-xs text-muted-foreground">
          커뮤니티 글은 뉴스 건수에 섞지 않고 신호로만 보여 줍니다. 봇·자동 게시 계정은 집계에서 뺍니다.
        </p>
      </header>
      <BuzzList clusters={view.clusters} />
    </main>
  );
}
