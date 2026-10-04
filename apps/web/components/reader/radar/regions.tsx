import Link from "next/link";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { StateBadge } from "@/components/reader/radar/parts";
import { REGION_LABEL } from "@/lib/format";
import {
  koreaGaps,
  koreaLagDays,
  last,
  radarHref,
  type RadarView,
  REGIONS,
  regionTotals,
  sameFocus,
  specialization,
  topicLabel,
} from "@/lib/radar";
import type { Radar, Topic } from "@/lib/reader-types";
import { cn } from "@/lib/utils";

/** Diverging fill for a location quotient on a log2 scale: warm = over-covered, cool = under. */
export function quotientFill(lq: number | null): string {
  if (lq === null) return "var(--muted)";
  const log = Math.max(-2, Math.min(2, Math.log2(Math.max(lq, 0.01))));
  const level = Math.round((Math.abs(log) / 2) * 75);
  return `color-mix(in oklab, var(${log >= 0 ? "--heat" : "--cool"}) ${level}%, var(--muted))`;
}

/** Theme × region: where each theme is over- or under-covered relative to all coverage. */
export function RegionLens({ radar, view, limit = 14 }: { radar: Radar; view: RadarView; limit?: number }) {
  const totals = regionTotals(radar);
  const regions = REGIONS.filter((r) => totals[r] > 0);
  const rows = radar.themes.filter((t) => last(t.counts) > 0).slice(0, limit);
  if (!rows.length || regions.length < 2) {
    return <p className="py-10 text-center text-sm text-muted-foreground">지역을 비교할 데이터가 부족합니다.</p>;
  }
  const all = regions.reduce((sum, r) => sum + totals[r], 0);
  return (
    <ChartTips>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-separate border-spacing-[2px] text-xs">
          <caption className="sr-only">테마별 지역 특화 지수(해당 지역 내 비중 ÷ 전체 비중)</caption>
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col" className="pb-1 text-left font-medium">테마</th>
              {regions.map((region) => (
                <th key={region} scope="col" className="pb-1 font-medium">
                  <span className={cn("block", region === "kr" && "font-bold text-foreground")}>{REGION_LABEL[region]}</span>
                  <span className="font-normal tabular-nums">{Math.round((totals[region] / all) * 100)}%</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((theme) => {
              const focus = { kind: "theme" as const, key: theme.key };
              const label = topicLabel("theme", theme);
              return (
                <tr key={theme.key}>
                  <th scope="row" className="max-w-44 pr-2 text-left font-medium">
                    <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus })} scroll={false} className={cn("block truncate hover:text-primary", sameFocus(view.focus, focus) && "font-bold text-primary")}>
                      {label}
                    </Link>
                  </th>
                  {regions.map((region) => {
                    const lq = specialization(theme, region, totals);
                    const count = theme.regions[region] ?? 0;
                    const strong = lq !== null && Math.abs(Math.log2(Math.max(lq, 0.01))) >= 1.2;
                    return (
                      <td
                        key={region}
                        aria-label={`${REGION_LABEL[region]} ${count}건, 특화 ${lq === null ? "-" : lq.toFixed(1)}배`}
                        data-tip={`${label} · ${REGION_LABEL[region]}\n${count}건 · 특화 ${lq === null ? "–" : `${lq.toFixed(2)}배`}\n${REGION_LABEL[region]} 보도의 ${totals[region] ? ((count / totals[region]) * 100).toFixed(1) : 0}% (전체 평균 ${((last(theme.counts) / all) * 100).toFixed(1)}%)`}
                        className={cn("h-7 min-w-14 rounded-[5px] text-center tabular-nums", strong ? "font-semibold text-heat-ink" : "text-ink-2")}
                        style={{ background: quotientFill(lq) }}
                      >
                        {count || "·"}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>칸 숫자 = 건수 · 색 = 특화 지수 · 회색 = 기대 건수가 적어 판단 보류</span>
        <span className="ml-auto flex items-center gap-1.5" aria-hidden>
          <span>덜 다룸 ¼</span>
          {[0.25, 0.5, 1, 2, 4].map((lq) => (
            <span key={lq} className="h-3 w-6 rounded-sm" style={{ background: quotientFill(lq) }} />
          ))}
          <span>4× 더 다룸</span>
        </span>
      </div>
    </ChartTips>
  );
}

function WatchRow({ radar, view, topic, note }: { radar: Radar; view: RadarView; topic: Topic; note: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 rounded-lg bg-muted/60 px-2.5 py-1.5 text-sm">
      <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus: { kind: "keyword", key: topic.key } })} scroll={false} className="min-w-0 flex-1 truncate font-medium hover:text-primary">
        {topicLabel("keyword", topic)}
      </Link>
      <StateBadge state={topic.state} />
      <span className="text-xs text-muted-foreground tabular-nums">{note}</span>
    </li>
  );
}

/** Rising technologies with no Korean source yet, and new ones Korea picked up late. */
export function KoreaWatch({ radar, view }: { radar: Radar; view: RadarView }) {
  const gaps = koreaGaps(radar);
  const lagging = radar.keywords
    .filter((k) => k.state === "new" || k.state === "surging")
    .map((k) => ({ topic: k, lag: koreaLagDays(k) }))
    .filter((row): row is { topic: Topic; lag: number } => row.lag !== null && row.lag >= 1)
    .sort((a, b) => b.lag - a.lag)
    .slice(0, 6);
  return (
    <div className="space-y-4">
      <section>
        <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">국내 공백 · 해외에서 뜨는데 국내 출처 0건</h3>
        {gaps.length ? (
          <ul className="space-y-1.5">
            {gaps.map((topic) => (
              <WatchRow key={topic.key} radar={radar} view={view} topic={topic} note={`해외 ${last(topic.counts)}건`} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">없음: 뜨는 기술은 국내에서도 다뤄지고 있습니다.</p>
        )}
      </section>
      <section>
        <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">국내 반영 지연 · 해외 첫 보도 → 국내 첫 보도</h3>
        {lagging.length ? (
          <ul className="space-y-1.5">
            {lagging.map(({ topic, lag }) => (
              <WatchRow key={topic.key} radar={radar} view={view} topic={topic} note={`+${lag.toFixed(1)}일`} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">신규·급상승 기술 중 하루 이상 늦게 들어온 것이 없습니다.</p>
        )}
      </section>
    </div>
  );
}
