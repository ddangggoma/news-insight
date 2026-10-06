import { ChevronLeft, ChevronRight, Lightbulb, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { DepthToggle } from "@/components/reader/briefing-depth";
import { CollectionSummary, CompanyMoves, ContinuingStories, InsightCard, TldrBox, WatchBox } from "@/components/reader/briefing-extras";
import { StoryRow } from "@/components/reader/story-row";
import { Button } from "@/components/ui/button";
import { formatBriefingDate, formatDateTime, TRACK_LABEL } from "@/lib/format";
import { DEEP_ONLY, FROM_FIVE } from "@/lib/briefing-depth";
import type { PublicBriefing } from "@/lib/briefing-types";
import { isoWeekKey } from "@/lib/radar";

export function BriefingMain({ briefing }: { briefing: PublicBriefing }) {
  const week = isoWeekKey(briefing.briefing_date);
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <time dateTime={briefing.briefing_date} className="font-medium text-foreground">
            {formatBriefingDate(briefing.briefing_date)}
          </time>
          <span aria-hidden>·</span>
          <span>{formatDateTime(briefing.published_at)} 발행</span>
          <span className="inline-flex items-center gap-1 rounded bg-impact-opportunity/12 px-1.5 py-0.5 text-xs text-impact-opportunity">
            <ShieldCheck className="size-3.5" aria-hidden /> 품질 게이트 {briefing.gates_passed}/{briefing.gates_total}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2 whitespace-nowrap">
            <DepthToggle />
            <Button asChild={Boolean(briefing.previous_date)} variant="ghost" size="sm" disabled={!briefing.previous_date}>
              {briefing.previous_date ? (
                <Link href={`/briefings/${briefing.previous_date}`} aria-label="이전 브리핑">
                  <ChevronLeft className="size-4" /> 이전
                </Link>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <ChevronLeft className="size-4" /> 이전
                </span>
              )}
            </Button>
            <Button asChild={Boolean(briefing.next_date)} variant="ghost" size="sm" disabled={!briefing.next_date}>
              {briefing.next_date ? (
                <Link href={`/briefings/${briefing.next_date}`} aria-label="다음 브리핑">
                  다음 <ChevronRight className="size-4" />
                </Link>
              ) : (
                <span className="inline-flex items-center gap-1">
                  다음 <ChevronRight className="size-4" />
                </span>
              )}
            </Button>
          </div>
        </div>
        <h1 className="text-2xl leading-tight font-bold tracking-tight text-balance md:text-3xl">
          {briefing.headline ?? "오늘의 데일리 브리핑"}
        </h1>
        <TldrBox tldr={briefing.tldr} insights={briefing.insights} />
        <WatchBox watch={briefing.watch ?? []} refs={briefing.refs} />
        <div className="group-data-[depth=five]/brief:hidden group-data-[depth=deep]/brief:hidden">
          <CompanyMoves moves={briefing.companies} compact week={week} />
        </div>
        {briefing.overview ? <p className={`leading-relaxed text-pretty text-foreground/85 ${FROM_FIVE}`}>{briefing.overview}</p> : null}
      </header>

      {briefing.insights.length > 0 ? (
        <section aria-labelledby="insights" className={`space-y-3 ${FROM_FIVE}`}>
          <h2 id="insights" className="flex items-center gap-2 text-lg font-semibold">
            <Lightbulb className="size-5 text-amber-500" aria-hidden /> 핵심 인사이트
          </h2>
          <ol className="grid gap-3 md:grid-cols-2 [&>*]:min-w-0">
            {briefing.insights.map((insight, index) => (
              <InsightCard key={index} insight={insight} index={index} refs={briefing.refs} />
            ))}
          </ol>
        </section>
      ) : null}

      <div className={`space-y-8 ${FROM_FIVE}`}>
        <CompanyMoves moves={briefing.companies} week={week} />
        <ContinuingStories stories={briefing.continuing} />
      </div>

      <div className={`space-y-8 ${DEEP_ONLY}`}>
      {briefing.sections.map((section) => (
        <section key={section.track} aria-labelledby={`track-${section.track}`} className="space-y-3">
          <div className="flex items-baseline justify-between gap-2 border-b pb-2">
            <h2 id={`track-${section.track}`} className="text-lg font-semibold">
              {TRACK_LABEL[section.track] ?? section.track}
            </h2>
            <span className="text-sm text-muted-foreground">{section.items.length}건</span>
          </div>
          {section.summary ? <p className="text-sm leading-relaxed text-muted-foreground">{section.summary}</p> : null}
          <div className="border-t">
            {section.items.map((item) => (
              <StoryRow key={item.id} item={item} />
            ))}
          </div>
        </section>
      ))}
        <CollectionSummary tracks={briefing.digest_tracks} refs={briefing.refs} />
      </div>
    </div>
  );
}
