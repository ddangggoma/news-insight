import { EmptyState } from "@/components/console/empty-state";
import { ReaderCard } from "@/components/reader/reader-card";
import type { ReaderCard as Card } from "@/lib/reader-types";

export function CardList({ cards, showTrack = false, empty }: { cards: Card[]; showTrack?: boolean; empty?: string }) {
  if (cards.length === 0) return <EmptyState title={empty ?? "기사가 없습니다"} />;
  return (
    <div className="grid gap-3 2xl:grid-cols-2 [&>*]:min-w-0">
      {cards.map((card) => (
        <ReaderCard key={card.id} card={card} showTrack={showTrack} />
      ))}
    </div>
  );
}
