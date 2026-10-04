import { Clock } from "lucide-react";

import { CardList } from "@/components/reader/card-list";
import type { ReaderCard } from "@/lib/reader-types";

/** Before the first briefing passes its gates: the newest classified cards, unranked. */
export function LatestFallback({ cards }: { cards: ReaderCard[] }) {
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Daily IT Intelligence</h1>
        <p className="flex items-start gap-2 rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">
          <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
          매일 04:40 KST 후보 동결, 05:00 KST 정시 발행. 품질 게이트를 통과한 첫 브리핑을 준비하고 있습니다. 아래는 최근 수집·분류된 기사입니다.
        </p>
      </header>
      <CardList cards={cards} showTrack empty="아직 분류된 기사가 없습니다" />
    </div>
  );
}
