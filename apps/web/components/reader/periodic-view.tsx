import { ArrowDown, ArrowRight, ArrowUp, ChevronLeft, ChevronRight, Eye, ListChecks, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { EvidenceLinks } from "@/components/console/evidence-links";
import type { PeriodKind, PublicPeriodic, Trajectory } from "@/lib/briefing-types";
import { formatBriefingDate } from "@/lib/format";

const BASE: Record<PeriodKind, string> = { week: "/briefings/weekly", month: "/briefings/monthly" };

const TRAJECTORY: Record<Trajectory, { label: string; icon: ReactNode; tone: string }> = {
  new: { label: "새 흐름", icon: <Sparkles className="size-3" aria-hidden />, tone: "bg-primary/10 text-primary" },
  rising: { label: "커지는 중", icon: <ArrowUp className="size-3" aria-hidden />, tone: "bg-impact-opportunity/12 text-impact-opportunity" },
  steady: { label: "유지", icon: <ArrowRight className="size-3" aria-hidden />, tone: "bg-muted text-muted-foreground" },
  fading: { label: "잦아듦", icon: <ArrowDown className="size-3" aria-hidden />, tone: "bg-muted text-muted-foreground" },
  reversal: { label: "방향 전환", icon: <RefreshCw className="size-3" aria-hidden />, tone: "bg-impact-risk/12 text-impact-risk" },
};

export function periodTitle(kind: PeriodKind, key: string): string {
  const week = /^(\d{4})-W(\d{2})$/.exec(key);
  if (kind === "week" && week) return `${week[1]}년 ${Number(week[2])}주차 주간 브리핑`;
  const month = /^(\d{4})-(\d{2})$/.exec(key);
  if (kind === "month" && month) return `${month[1]}년 ${Number(month[2])}월 월간 브리핑`;
  return kind === "week" ? "주간 브리핑" : "월간 브리핑";
}

function Bullets({ icon, title, lines }: { icon: ReactNode; title: string; lines: string[] }) {
  if (!lines.length) return null;
  return (
    <section className="space-y-2 rounded-xl border bg-card p-4">
      <h2 className="flex items-center gap-2 font-semibold">
        {icon} {title}
      </h2>
      <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed">
        {lines.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

export function PeriodicView({ period }: { period: PublicPeriodic }) {
  const { content } = period;
  const base = BASE[period.kind];
  return (
    <main className="mx-auto w-full min-w-0 max-w-3xl space-y-5 px-4 py-6 md:px-6">
      <header className="space-y-2">
        <p className="text-sm text-muted-foreground">
          {periodTitle(period.kind, period.key)} · {formatBriefingDate(period.period_start)} ~ {formatBriefingDate(period.period_end)} · 일일 브리핑 {period.days}건
        </p>
        <h1 className="text-2xl font-bold leading-snug">{content.headline}</h1>
      </header>
      {content.tldr.length ? (
        <section aria-label="핵심 3줄" className="rounded-xl border bg-muted/30 p-4">
          <ol className="space-y-2">
            {content.tldr.map((line, index) => (
              <li key={index} className="flex gap-2 text-[15px] leading-relaxed">
                <span className="font-semibold text-primary tabular-nums">{index + 1}</span>
                <span className="min-w-0">{line}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <p className="text-sm leading-relaxed text-muted-foreground">{content.overview}</p>
      {content.trends.length ? (
        <section aria-labelledby="trends-title" className="space-y-3">
          <h2 id="trends-title" className="text-lg font-semibold">
            기간의 흐름
          </h2>
          {content.trends.map((trend, index) => {
            const meta = TRAJECTORY[trend.trajectory] ?? TRAJECTORY.steady;
            return (
              <article key={index} className="space-y-2 rounded-xl border bg-card p-4">
                <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                  {trend.title}
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${meta.tone}`}>
                    {meta.icon} {meta.label}
                  </span>
                </h3>
                <p className="text-sm leading-relaxed">{trend.body}</p>
                {trend.companies.length ? <p className="text-xs text-muted-foreground">관련 기업: {trend.companies.join(", ")}</p> : null}
                <EvidenceLinks ids={trend.item_ids} items={period.refs} />
              </article>
            );
          })}
        </section>
      ) : null}
      {content.companies.length ? (
        <section aria-labelledby="companies-title" className="space-y-2 rounded-xl border bg-card p-4">
          <h2 id="companies-title" className="font-semibold">
            기업 움직임
          </h2>
          <ul className="space-y-3">
            {content.companies.map((company) => (
              <li key={company.name} className="space-y-1">
                <p className="text-sm">
                  <span className="font-medium">{company.name}</span> <span className="text-muted-foreground">{company.summary}</span>
                </p>
                <EvidenceLinks ids={company.item_ids} items={period.refs} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        <Bullets icon={<Eye className="size-4 text-primary" aria-hidden />} title="다음에 볼 신호" lines={content.watch_next} />
        <Bullets icon={<ListChecks className="size-4 text-primary" aria-hidden />} title="센싱 실무 할 일" lines={content.actions} />
      </div>
      {period.daily.length ? (
        <section aria-labelledby="daily-title" className="space-y-2">
          <h2 id="daily-title" className="text-sm font-semibold">
            이 기간의 일일 브리핑
          </h2>
          <ol className="space-y-1 text-sm">
            {period.daily.map((day) => (
              <li key={day.briefing_date}>
                <Link href={`/briefings/${day.briefing_date}`} className="flex gap-3 rounded-md px-2 py-1.5 hover:bg-muted">
                  <span className="w-24 shrink-0 text-xs text-muted-foreground">{formatBriefingDate(day.briefing_date)}</span>
                  <span className="line-clamp-1 min-w-0">{day.headline ?? "데일리 브리핑"}</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <nav aria-label="기간 이동" className="flex justify-between text-sm">
        {period.previous_key ? (
          <Link href={`${base}/${period.previous_key}`} className="inline-flex items-center gap-1 hover:underline">
            <ChevronLeft className="size-4" aria-hidden /> {periodTitle(period.kind, period.previous_key)}
          </Link>
        ) : (
          <span />
        )}
        {period.next_key ? (
          <Link href={`${base}/${period.next_key}`} className="inline-flex items-center gap-1 hover:underline">
            {periodTitle(period.kind, period.next_key)} <ChevronRight className="size-4" aria-hidden />
          </Link>
        ) : null}
      </nav>
    </main>
  );
}

export function PeriodicLinks({ entries }: { entries: { kind: PeriodKind; key: string; headline: string }[] }) {
  return (
    <ol className="space-y-1 text-sm">
      {entries.map((entry) => (
        <li key={`${entry.kind}-${entry.key}`}>
          <Link href={`${BASE[entry.kind]}/${entry.key}`} className="block rounded-md px-2 py-1.5 hover:bg-muted">
            <span className="block text-xs text-muted-foreground">{periodTitle(entry.kind, entry.key)}</span>
            <span className="line-clamp-1">{entry.headline}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
