import { CalendarDays, Compass, Map as MapIcon, TrendingUp, Users } from "lucide-react";
import type { ReactNode } from "react";

import { EvidenceLinks } from "@/components/console/evidence-links";
import Link from "next/link";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { BriefingEntry, BriefingPersona, PublicBriefing } from "@/lib/briefing-types";
import { formatBriefingDate } from "@/lib/format";
import { FIELD_LABEL, IMPACT_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const GROUPS = [
  ["executive", "경영진"],
  ["business", "사업부장"],
  ["domain", "도메인"],
] as const;
const HORIZONS = [
  ["1y", "1년"],
  ["3y", "3년"],
  ["5y", "5년"],
] as const;
const fieldLabel = (key: string) => FIELD_LABEL[key] ?? key;
const IMPACT_STYLE: Record<string, string> = {
  opportunity: "bg-impact-opportunity/12 text-impact-opportunity",
  risk: "bg-impact-risk/12 text-impact-risk",
};
const IMPACT_BAR: Record<string, string> = {
  opportunity: "bg-impact-opportunity",
  risk: "bg-impact-risk",
  watch: "bg-impact-watch",
};

function Panel({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded-xl border bg-card p-4">
      <h2 className="flex items-center gap-2 font-semibold">
        {icon} {title}
      </h2>
      {children}
    </section>
  );
}

function PersonaList({ personas, refs }: { personas: BriefingPersona[]; refs: PublicBriefing["refs"] }) {
  const insights = personas.filter((p) => p.status === "insight");
  const quiet = personas.length - insights.length;
  return (
    <div className="space-y-3">
      {insights.map((persona) => (
        <details key={persona.key} className="group/persona rounded-lg border p-3 open:bg-muted/30">
          <summary className="cursor-pointer list-none space-y-1 [&::-webkit-details-marker]:hidden">
            <p className="text-xs font-medium text-primary">{persona.name}</p>
            <p className="text-sm leading-snug font-semibold">{persona.headline}</p>
          </summary>
          <div className="mt-2 space-y-2 text-sm">
            <p className="leading-relaxed text-foreground/85">{persona.insight}</p>
            {persona.actions.length > 0 ? (
              <ul className="list-disc space-y-0.5 pl-4 text-foreground/80">
                {persona.actions.map((action, index) => (
                  <li key={index}>{action}</li>
                ))}
              </ul>
            ) : null}
            <EvidenceLinks ids={persona.item_ids} items={refs} />
          </div>
        </details>
      ))}
      {quiet > 0 ? <p className="text-xs text-muted-foreground">신호 없음(no_signal) {quiet}명</p> : null}
    </div>
  );
}

function citations(briefing: PublicBriefing): [number, number][] {
  const counts = new Map<number, number>();
  const add = (ids: number[]) => ids.forEach((id) => counts.set(id, (counts.get(id) ?? 0) + 1));
  briefing.insights.forEach((insight) => add(insight.item_ids));
  briefing.strategy?.personas.filter((p) => p.status === "insight").forEach((p) => add(p.item_ids));
  const report = briefing.strategy?.report;
  if (report) {
    [...(report.fields ?? []).flatMap((f) => f.claims), ...report.roadmap, ...report.opportunities, ...report.risks].forEach(
      (claim) => add(claim.item_ids),
    );
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
}

function EvidenceMap({ briefing }: { briefing: PublicBriefing }) {
  const top = citations(briefing);
  if (top.length === 0) return <p className="text-sm text-muted-foreground">인용된 근거가 없습니다.</p>;
  const refs = new Map(briefing.refs.map((ref) => [ref.id, ref]));
  const titles = new Map(briefing.sections.flatMap((s) => s.items).map((c) => [c.id, c.title_ko || c.title]));
  const max = top[0][1];
  return (
    <ol className="space-y-2">
      {top.map(([id, count]) => {
        const ref = refs.get(id);
        if (!ref) return null;
        return (
          <li key={id} className="space-y-1">
            <a href={ref.url} target="_blank" rel="noopener noreferrer" className="line-clamp-2 text-sm leading-snug hover:underline">
              {titles.get(id) ?? ref.title}
            </a>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="h-1.5 rounded-full bg-primary/70" style={{ width: `${(count / max) * 60}%` }} aria-hidden />
              <span className="shrink-0">
                {ref.source_name} · 인용 {count}회
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function MarketImpact({ briefing }: { briefing: PublicBriefing }) {
  const cards = briefing.sections.flatMap((section) => section.items);
  const rows = Object.keys(FIELD_LABEL)
    .map((field) => {
      const mine = cards.filter((card) => card.field === field);
      const byImpact = Object.fromEntries(
        Object.keys(IMPACT_LABEL).map((impact) => [impact, mine.filter((c) => c.impact === impact).length]),
      );
      return { field, total: mine.length, byImpact };
    })
    .filter((row) => row.total > 0)
    .sort((a, b) => b.total - a.total);
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">기술 분야로 분류된 기사가 없습니다.</p>;
  const max = Math.max(...rows.map((row) => row.total));
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.field} className="grid grid-cols-[112px_1fr_24px] items-center gap-2 text-xs">
          <span className="truncate font-medium" title={fieldLabel(row.field)}>{fieldLabel(row.field)}</span>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-muted" style={{ width: `${(row.total / max) * 100}%` }}>
            {Object.entries(row.byImpact).map(([impact, count]) =>
              count > 0 ? (
                <span key={impact} className={IMPACT_BAR[impact]} style={{ width: `${(count / row.total) * 100}%` }} title={`${IMPACT_LABEL[impact]} ${count}`} />
              ) : null,
            )}
          </div>
          <span className="text-right text-muted-foreground tabular-nums">{row.total}</span>
        </div>
      ))}
      <div className="flex gap-3 pt-1 text-[11px] text-muted-foreground">
        {Object.entries(IMPACT_LABEL).map(([impact, label]) => (
          <span key={impact} className="flex items-center gap-1">
            <span className={cn("size-2 rounded-full", IMPACT_BAR[impact])} aria-hidden /> {label}
          </span>
        ))}
      </div>
    </div>
  );
}

function PastBriefings({ entries, current }: { entries: BriefingEntry[]; current: string }) {
  if (entries.length < 2) return null;
  return (
    <ol className="space-y-1 text-sm">
      {entries.map((entry) => (
        <li key={entry.briefing_date}>
          <Link
            href={`/briefings/${entry.briefing_date}`}
            aria-current={entry.briefing_date === current ? "page" : undefined}
            className="block rounded-md px-2 py-1.5 hover:bg-muted aria-[current=page]:bg-muted aria-[current=page]:font-semibold"
          >
            <span className="block text-xs text-muted-foreground">{formatBriefingDate(entry.briefing_date)}</span>
            <span className="line-clamp-1">{entry.headline ?? "데일리 브리핑"}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

export function BriefingAside({ briefing, past }: { briefing: PublicBriefing; past: BriefingEntry[] }) {
  const strategy = briefing.strategy;
  const report = strategy?.report;
  return (
    <div className="space-y-4">
      {strategy ? (
        <Panel icon={<Users className="size-4 text-primary" aria-hidden />} title="페르소나 통찰">
          <Tabs defaultValue="executive" className="gap-3">
            <TabsList className="grid w-full grid-cols-3">
              {GROUPS.map(([group, label]) => (
                <TabsTrigger key={group} value={group}>
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
            {GROUPS.map(([group]) => (
              <TabsContent key={group} value={group}>
                <PersonaList personas={strategy.personas.filter((p) => p.group === group)} refs={briefing.refs} />
              </TabsContent>
            ))}
          </Tabs>
        </Panel>
      ) : null}
      {report ? (
        <Panel icon={<Compass className="size-4 text-primary" aria-hidden />} title="전략 요약">
          <p className="text-sm leading-relaxed text-foreground/85">{report.summary}</p>
          {strategy?.review_verdict ? (
            <p className="text-xs text-muted-foreground">
              독립 리뷰 {strategy.review_verdict === "pass" ? "통과" : `반영 (주장 ${strategy.dropped_claims}건 제외)`}
            </p>
          ) : null}
        </Panel>
      ) : null}
      <Panel icon={<MapIcon className="size-4 text-primary" aria-hidden />} title="근거 지도">
        <EvidenceMap briefing={briefing} />
      </Panel>
      {report && report.roadmap.length > 0 ? (
        <Panel icon={<TrendingUp className="size-4 text-primary" aria-hidden />} title="로드맵 시사점">
          <div className="space-y-3">
            {HORIZONS.map(([horizon, label]) => {
              const entries = report.roadmap.filter((entry) => entry.horizon === horizon);
              if (entries.length === 0) return null;
              return (
                <div key={horizon} className="space-y-1.5">
                  <p className="text-xs font-semibold text-muted-foreground">{label}</p>
                  <ul className="space-y-2 border-l-2 pl-3 text-sm">
                    {entries.map((entry) => (
                      <li key={entry.id} className="space-y-1">
                        <p className="leading-snug">{entry.text}</p>
                        <EvidenceLinks ids={entry.item_ids} items={briefing.refs} />
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </Panel>
      ) : null}
      <Panel icon={<TrendingUp className="size-4 text-primary" aria-hidden />} title="시장 영향도">
        <MarketImpact briefing={briefing} />
        {report && (report.opportunities.length > 0 || report.risks.length > 0) ? (
          <div className="space-y-2 border-t pt-3 text-sm">
            {report.opportunities.slice(0, 3).map((claim) => (
              <p key={claim.id} className="flex gap-2">
                <span className={cn("h-fit shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium", IMPACT_STYLE.opportunity)}>기회</span>
                <span className="leading-snug">{claim.text}</span>
              </p>
            ))}
            {report.risks.slice(0, 3).map((claim) => (
              <p key={claim.id} className="flex gap-2">
                <span className={cn("h-fit shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium", IMPACT_STYLE.risk)}>위험</span>
                <span className="leading-snug">{claim.text}</span>
              </p>
            ))}
          </div>
        ) : null}
      </Panel>
      {past.length > 1 ? (
        <Panel icon={<CalendarDays className="size-4 text-primary" aria-hidden />} title="지난 브리핑">
          <PastBriefings entries={past} current={briefing.briefing_date} />
        </Panel>
      ) : null}
    </div>
  );
}
