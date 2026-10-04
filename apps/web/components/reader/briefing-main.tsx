import { ChevronLeft, ChevronRight, Lightbulb, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { EvidenceLinks } from "@/components/console/evidence-links";
import { StoryRow } from "@/components/reader/story-row";
import { Button } from "@/components/ui/button";
import { formatBriefingDate, formatDateTime, TRACK_LABEL } from "@/lib/format";
import type { PublicBriefing } from "@/lib/briefing-types";

export function BriefingMain({ briefing }: { briefing: PublicBriefing }) {
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
          <div className="ml-auto flex gap-1 whitespace-nowrap">
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
        {briefing.overview ? <p className="leading-relaxed text-pretty text-foreground/85">{briefing.overview}</p> : null}
      </header>

      {briefing.insights.length > 0 ? (
        <section aria-labelledby="insights" className="space-y-3">
          <h2 id="insights" className="flex items-center gap-2 text-lg font-semibold">
            <Lightbulb className="size-5 text-amber-500" aria-hidden /> 핵심 인사이트
          </h2>
          <ol className="grid gap-3 md:grid-cols-2 [&>*]:min-w-0">
            {briefing.insights.map((insight, index) => (
              <li key={index} className="space-y-2 rounded-xl border bg-muted/30 p-4">
                <p className="font-semibold">
                  <span className="mr-2 text-primary tabular-nums">{index + 1}</span>
                  {insight.title}
                </p>
                <p className="text-sm leading-relaxed text-foreground/85">{insight.body}</p>
                <EvidenceLinks ids={insight.item_ids} items={briefing.refs} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}

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
    </div>
  );
}
