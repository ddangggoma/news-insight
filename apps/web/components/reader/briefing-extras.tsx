import Link from "next/link";

import { EvidenceLinks } from "@/components/console/evidence-links";
import type { BriefingInsight, CompanyMove, Continuity, ContinuingStory, DigestTrack, ItemRef, Strength } from "@/lib/briefing-types";
import { RELATION_META } from "@/lib/companies";
import { TRACK_LABEL } from "@/lib/format";
import { radarHref } from "@/lib/radar";
import { cn } from "@/lib/utils";

const STRENGTH_META: Record<Strength["grade"], { label: string; className: string }> = {
  strong: { label: "근거 강함", className: "bg-impact-opportunity/12 text-impact-opportunity" },
  medium: { label: "근거 보통", className: "bg-amber-500/12 text-amber-700 dark:text-amber-300" },
  weak: { label: "근거 약함", className: "bg-muted text-muted-foreground" },
};

const CONTINUITY_META: Record<Continuity, { label: string; className: string }> = {
  new: { label: "새로 등장", className: "bg-primary/12 text-primary" },
  continuing: { label: "이어짐", className: "bg-muted text-ink-2" },
  escalation: { label: "확대", className: "bg-state-hot/12 text-state-hot" },
  reversal: { label: "반전", className: "bg-impact-risk/12 text-impact-risk" },
};

export function StrengthBadge({ strength }: { strength: Pick<Strength, "grade" | "reason"> | null | undefined }) {
  if (!strength) return null;
  const meta = STRENGTH_META[strength.grade];
  return (
    <span title={strength.reason} className={cn("inline-flex rounded-full px-2 py-px text-[11px] font-semibold whitespace-nowrap", meta.className)}>
      {meta.label}
    </span>
  );
}

export function ContinuityBadge({ continuity, previous }: { continuity: Continuity; previous?: string | null }) {
  const meta = CONTINUITY_META[continuity];
  return (
    <span
      title={previous ? `이전: ${previous}` : undefined}
      className={cn("inline-flex rounded-full px-2 py-px text-[11px] font-semibold whitespace-nowrap", meta.className)}
    >
      {meta.label}
    </span>
  );
}

/** One-minute view: the three takeaways (or the first insight titles when an older briefing has none). */
export function TldrBox({ tldr, insights }: { tldr: string[]; insights: BriefingInsight[] }) {
  const lines = tldr.length ? tldr.map((text) => ({ text, insight: null as BriefingInsight | null })) : insights.slice(0, 3).map((insight) => ({ text: insight.title, insight }));
  if (!lines.length) return null;
  return (
    <section aria-label="핵심 3줄" className="rounded-xl border bg-muted/30 p-4">
      <ol className="space-y-2">
        {lines.map((line, index) => (
          <li key={index} className="flex gap-2 text-[15px] leading-relaxed">
            <span className="font-semibold text-primary tabular-nums">{index + 1}</span>
            <span className="min-w-0">
              {line.text}
              {line.insight ? (
                <span className="ml-1.5 inline-flex gap-1 align-middle">
                  <ContinuityBadge continuity={line.insight.continuity} previous={line.insight.previous_title} />
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function InsightCard({ insight, index, refs }: { insight: BriefingInsight; index: number; refs: ItemRef[] }) {
  return (
    <li className="space-y-2 rounded-xl border bg-muted/30 p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <ContinuityBadge continuity={insight.continuity} previous={insight.previous_title} />
        <StrengthBadge strength={insight.strength} />
        {insight.strength ? <span className="text-[11px] text-muted-foreground">{insight.strength.reason}</span> : null}
      </div>
      <p className="font-semibold">
        <span className="mr-2 text-primary tabular-nums">{index + 1}</span>
        {insight.title}
      </p>
      {insight.previous_title && insight.continuity !== "new" ? (
        <p className="text-xs text-muted-foreground">이전 브리핑: {insight.previous_title}</p>
      ) : null}
      <p className="text-sm leading-relaxed text-foreground/85">{insight.body}</p>
      {insight.companies.length ? (
        <p className="flex flex-wrap gap-1 text-xs text-ink-2">
          {insight.companies.map((name) => (
            <span key={name} className="rounded bg-muted px-1.5 py-px">
              {name}
            </span>
          ))}
        </p>
      ) : null}
      <EvidenceLinks ids={insight.item_ids} items={refs} />
    </li>
  );
}

export function CompanyMoves({ moves, compact = false, week }: { moves: CompanyMove[]; compact?: boolean; week: string }) {
  if (!moves.length) return null;
  const shown = compact ? moves.slice(0, 3) : moves;
  return (
    <section aria-labelledby={compact ? undefined : "company-moves"} className="space-y-2">
      {compact ? null : (
        <h2 id="company-moves" className="text-lg font-semibold">
          기업 움직임
        </h2>
      )}
      <ul className={cn("flex flex-wrap gap-2", compact ? "" : "")}>
        {shown.map((move) => (
          <li key={move.key}>
            <Link
              href={radarHref("week", week, { focus: { kind: "company", key: move.key } })}
              className="inline-flex items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-sm hover:border-primary/40"
            >
              <span aria-hidden className="size-2 rounded-full" style={{ background: RELATION_META[move.relation].color }} />
              <span className="font-medium">{move.label}</span>
              <span className="text-xs text-muted-foreground">
                {RELATION_META[move.relation].label} · {move.count}건
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ContinuingStories({ stories }: { stories: ContinuingStory[] }) {
  if (!stories.length) return null;
  return (
    <section aria-labelledby="continuing" className="space-y-2">
      <h2 id="continuing" className="text-lg font-semibold">
        이어지는 이야기
      </h2>
      <ul className="divide-y rounded-xl border">
        {stories.map((story) => (
          <li key={story.story_id}>
            <Link href={`/items/${story.item_id}`} className="flex items-baseline justify-between gap-3 px-4 py-2.5 hover:bg-muted/40">
              <span className="min-w-0 text-sm leading-snug">{story.title}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {story.days}일째 · 출처 {story.sources}곳
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The whole-collection summary by track and category (formerly the digest page, plan 13 C2). */
export function CollectionSummary({ tracks, refs }: { tracks: DigestTrack[]; refs: ItemRef[] }) {
  if (!tracks.length) return null;
  return (
    <section id="summary" aria-labelledby="summary-title" className="scroll-mt-24 space-y-4">
      <h2 id="summary-title" className="text-lg font-semibold">
        전체 수집 요약
      </h2>
      {tracks.map((track) => (
        <div key={track.track} className="space-y-2">
          <h3 className="font-semibold">{TRACK_LABEL[track.track] ?? track.track}</h3>
          <p className="text-sm leading-relaxed text-muted-foreground">{track.summary}</p>
          {track.categories.map((category) => (
            <div key={category.category} className="space-y-1.5 border-l-2 pl-3">
              <p className="text-sm font-medium">{category.headline}</p>
              <ul className="space-y-1.5">
                {category.points.map((point, index) => (
                  <li key={index} className="space-y-1 text-sm text-foreground/85">
                    <p>{point.text}</p>
                    <EvidenceLinks ids={point.item_ids} items={refs} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}
