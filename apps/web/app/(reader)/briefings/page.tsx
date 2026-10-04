import { Clock } from "lucide-react";
import type { Metadata } from "next";

import { BriefingAside } from "@/components/reader/briefing-aside";
import { BriefingMain } from "@/components/reader/briefing-main";
import { BriefingPanes } from "@/components/reader/briefing-panes";
import { briefings } from "@/lib/briefings";

export const metadata: Metadata = { title: "데일리 브리핑" };
// Rendered per request (data still comes from the reader cache): the build has no API key.
export const dynamic = "force-dynamic";

export default async function LatestBriefingPage() {
  const [briefing, past] = await Promise.all([briefings.latest(), briefings.recent()]);
  if (!briefing) {
    return (
      <main className="mx-auto max-w-3xl space-y-3 px-4 py-10 md:px-6">
        <h1 className="text-2xl font-bold">데일리 브리핑</h1>
        <p className="flex items-start gap-2 rounded-lg border bg-muted/40 p-4 text-sm text-muted-foreground">
          <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
          매일 04:40 KST 후보 동결, 05:00 KST 발행. 품질 게이트를 모두 통과한 브리핑만 공개되며, 아직 발행된 브리핑이 없습니다.
        </p>
      </main>
    );
  }
  return <BriefingPanes main={<BriefingMain briefing={briefing} />} aside={<BriefingAside briefing={briefing} past={past} />} />;
}
