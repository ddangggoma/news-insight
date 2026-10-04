import Link from "next/link";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { Legend, StateBadge } from "@/components/reader/radar/parts";
import { TRACK_LABEL } from "@/lib/format";
import {
  formatPoints,
  formatZ,
  last,
  periodLabel,
  radarHref,
  type RadarView,
  researchShare,
  sameFocus,
  shareSeries,
  STAGE_META,
  stageOf,
  sumMix,
  topicLabel,
} from "@/lib/radar";
import type { Radar, Topic } from "@/lib/reader-types";
import type { Track } from "@/lib/types";
import { IMPACT_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

/** Research first so the left part of every bar is the research + open source share. */
const TRACK_ORDER: Track[] = ["research_ip", "oss", "community", "news"];
const TRACK_FILL: Record<Track, string> = {
  research_ip: "var(--viz-research)",
  oss: "var(--viz-oss)",
  community: "var(--viz-community)",
  news: "var(--viz-news)",
};
const IMPACT_FILL = { opportunity: "var(--impact-opportunity)", risk: "var(--impact-risk)", watch: "var(--impact-watch)" } as const;

function Area({ values, max, periods }: { values: number[]; max: number; periods: string[] }) {
  const W = 160, H = 44;
  const step = W / (values.length - 1);
  const y = (v: number) => H - 2 - (v / (max || 1)) * (H - 6);
  const line = values.map((v, i) => `${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-11 w-full" preserveAspectRatio="none" aria-hidden>
      <line x1={0} x2={W} y1={H - 2} y2={H - 2} stroke="var(--border)" />
      <polygon points={`0,${H - 2} ${line} ${W},${H - 2}`} fill="var(--primary)" fillOpacity={0.1} />
      <polyline points={line} fill="none" stroke="var(--primary)" strokeWidth={2} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {values.map((v, i) => (
        <rect key={periods[i]} x={i * step - step / 2} y={0} width={step} height={H} fill="transparent" data-tip={`${periodLabel(periods[i])}\n${v.toFixed(1)}%`} />
      ))}
    </svg>
  );
}

/** Share of voice per category on one shared scale: who is gaining attention, who is losing it. */
export function CategoryShare({ radar, view }: { radar: Radar; view: RadarView }) {
  const fields = radar.fields.filter((f) => f.counts.some((c) => c > 0));
  if (!fields.length) return <p className="py-10 text-center text-sm text-muted-foreground">표시할 카테고리가 없습니다.</p>;
  const series = new Map(fields.map((f) => [f.key, shareSeries(f, radar.kpis.items)]));
  const max = Math.max(...[...series.values()].flat(), 1);
  const ordered = [...fields].sort((a, b) => last(series.get(b.key)!) - last(series.get(a.key)!));
  return (
    <ChartTips>
      <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-5">
        {ordered.map((field) => {
          const values = series.get(field.key)!;
          const delta = last(values) - (values[values.length - 2] ?? 0);
          const impacts = field.impacts;
          const impactTotal = impacts.opportunity + impacts.risk + impacts.watch;
          const focus = { kind: "field" as const, key: field.key };
          return (
            <li key={field.key}>
              <Link
                href={radarHref(radar.window.kind, radar.window.key, { ...view, focus })}
                scroll={false}
                className={cn(
                  "flex h-full flex-col gap-1 rounded-xl border p-2.5 transition hover:border-primary/40 hover:bg-muted/40",
                  sameFocus(view.focus, focus) && "border-primary bg-primary/5",
                )}
              >
                <span className="flex items-start justify-between gap-1">
                  <span className="text-xs leading-snug font-semibold">{topicLabel("field", field)}</span>
                  <StateBadge state={field.state} />
                </span>
                <span className="flex items-baseline gap-1.5">
                  <span className="text-lg leading-none font-bold">{last(values).toFixed(1)}%</span>
                  <span className={cn("text-[11px] tabular-nums", delta > 0.05 ? "text-impact-opportunity" : delta < -0.05 ? "text-impact-risk" : "text-muted-foreground")}>
                    {formatPoints(delta)}
                  </span>
                </span>
                <Area values={values} max={max} periods={radar.periods} />
                {impactTotal ? (
                  <span
                    className="flex h-1.5 gap-0.5 overflow-hidden rounded-full"
                    data-tip={`${topicLabel("field", field)} 영향\n기회 ${impacts.opportunity} · 위험 ${impacts.risk} · 관찰 ${impacts.watch}`}
                  >
                    {(["opportunity", "risk", "watch"] as const).map((impact) =>
                      impacts[impact] ? <span key={impact} style={{ flex: impacts[impact], background: IMPACT_FILL[impact] }} /> : null,
                    )}
                  </span>
                ) : null}
                <span className="text-[11px] text-muted-foreground tabular-nums">
                  {last(field.counts)}건 · {formatZ(field.z)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <Legend className="mt-3" items={(["opportunity", "risk", "watch"] as const).map((impact) => ({ label: `${IMPACT_LABEL[impact]} (영향 막대)`, swatch: IMPACT_FILL[impact] }))} />
    </ChartTips>
  );
}

function MixBar({ topic, label }: { topic: Topic; label: string }) {
  const total = sumMix(topic.tracks);
  const before = researchShare(topic.previous_tracks);
  return (
    <div className="relative h-4">
      <div className="flex h-full gap-0.5 overflow-hidden rounded-[4px]">
        {TRACK_ORDER.map((track) =>
          topic.tracks[track] ? (
            <span
              key={track}
              data-tip={`${label} · ${TRACK_LABEL[track]}\n${topic.tracks[track]}건 (${Math.round((topic.tracks[track] / total) * 100)}%)`}
              style={{ flex: topic.tracks[track], background: TRACK_FILL[track] }}
            />
          ) : null,
        )}
      </div>
      {before !== null ? (
        <span
          className="pointer-events-none absolute -inset-y-1 w-0.5 rounded-full bg-foreground"
          style={{ left: `calc(${(before * 100).toFixed(1)}% - 1px)` }}
          title={`직전 기간 논문·오픈소스 ${Math.round(before * 100)}%`}
        />
      ) : null}
    </div>
  );
}

/**
 * Where each theme sits on the research → market path: the track mix of this period's reports,
 * with a tick where the research + open source share was one period earlier.
 */
export function MaturityBars({ radar, view, limit = 14 }: { radar: Radar; view: RadarView; limit?: number }) {
  const rows = radar.themes
    .filter((t) => sumMix(t.tracks) >= 3)
    .sort((a, b) => last(b.counts) - last(a.counts))
    .slice(0, limit)
    .sort((a, b) => (researchShare(b.tracks) ?? 0) - (researchShare(a.tracks) ?? 0));
  if (!rows.length) return <p className="py-10 text-center text-sm text-muted-foreground">3건 이상 언급된 테마가 없습니다.</p>;
  return (
    <ChartTips>
      <ul className="space-y-2">
        {rows.map((theme) => {
          const share = researchShare(theme.tracks);
          const before = researchShare(theme.previous_tracks);
          const stage = stageOf(share);
          const focus = { kind: "theme" as const, key: theme.key };
          const label = topicLabel("theme", theme);
          return (
            <li key={theme.key} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_4.5rem] items-center gap-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_6.5rem]">
              <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus })} scroll={false} className={cn("truncate text-sm hover:text-primary", sameFocus(view.focus, focus) && "font-bold text-primary")}>
                {label}
              </Link>
              <MixBar topic={theme} label={label} />
              <span className="text-right text-xs leading-tight">
                <span className="block font-semibold">{stage ? STAGE_META[stage].label : "—"}</span>
                <span className="text-muted-foreground tabular-nums">
                  {share !== null ? `${Math.round(share * 100)}%` : ""}
                  {share !== null && before !== null ? ` (${formatPoints((share - before) * 100)})` : ""}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <Legend items={TRACK_ORDER.map((track) => ({ label: TRACK_LABEL[track], swatch: TRACK_FILL[track] }))} />
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="inline-block h-3 w-0.5 rounded-full bg-foreground" aria-hidden /> 직전 기간 논문·오픈소스 비중
        </span>
      </div>
    </ChartTips>
  );
}
