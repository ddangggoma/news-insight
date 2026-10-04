import Link from "next/link";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { Legend } from "@/components/reader/radar/parts";
import { TRACK_LABEL } from "@/lib/format";
import { last, netOpportunity, periodLabel, radarHref, type RadarView, rankSeries, sameFocus, topicLabel } from "@/lib/radar";
import type { Radar } from "@/lib/reader-types";
import type { Track } from "@/lib/types";
import { IMPACT_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const TRACK_FILL: Record<Track, string> = {
  research_ip: "var(--viz-research)",
  oss: "var(--viz-oss)",
  community: "var(--viz-community)",
  news: "var(--viz-news)",
};
const PIPELINE: Track[] = ["research_ip", "oss", "community", "news"];

// ── rank bump chart ──────────────────────────────────────────────────────────────────────

/** Top themes by rank in every period: climbers in the warm hue, fallers in the cool one. */
export function RankBump({ radar, view, top = 10 }: { radar: Radar; view: RadarView; top?: number }) {
  const rows = rankSeries(radar.themes, top);
  if (rows.length < 2) return <p className="py-10 text-center text-sm text-muted-foreground">순위를 비교할 테마가 부족합니다.</p>;
  const W = 960, H = 40 + top * 28, L = 16, R = 200, T = 28, B = 12;
  const n = radar.periods.length;
  const x = (i: number) => L + (i / (n - 1)) * (W - L - R);
  const lanes = top + 1; // a theme outside the top counts as one place below it
  const y = (rank: number) => T + ((rank - 1) / (top - 1)) * (H - T - B);
  const move = (ranks: (number | null)[]) => Math.min(ranks[0] ?? lanes, lanes) - Math.min(last(ranks) ?? lanes, lanes);
  const tone = (delta: number) => (delta >= 3 ? "var(--state-hot)" : delta <= -3 ? "var(--state-cool)" : "var(--muted-foreground)");
  return (
    <ChartTips>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[680px]" role="img" aria-label={`언급량 상위 ${top}개 테마의 기간별 순위`}>
          {radar.periods.map((period, i) => (
            <g key={period}>
              <line x1={x(i)} x2={x(i)} y1={T - 8} y2={H - B} stroke="var(--border)" />
              <text x={x(i)} y={T - 14} fontSize={11} textAnchor="middle" fill={i === n - 1 ? "var(--foreground)" : "var(--muted-foreground)"}>
                {periodLabel(period)}
              </text>
            </g>
          ))}
          {[...rows]
            .sort((a, b) => Math.abs(move(a.ranks)) - Math.abs(move(b.ranks)))
            .map(({ topic, ranks }) => {
              const delta = move(ranks);
              const color = tone(delta);
              const focus = { kind: "theme" as const, key: topic.key };
              const selected = sameFocus(view.focus, focus);
              // break the line where the theme was outside the top instead of diving to the floor
              const segments: string[] = [];
              let run: string[] = [];
              ranks.forEach((rank, i) => {
                if (rank !== null && rank <= top) run.push(`${x(i).toFixed(1)},${y(rank).toFixed(1)}`);
                else {
                  if (run.length > 1) segments.push(run.join(" "));
                  run = [];
                }
              });
              if (run.length > 1) segments.push(run.join(" "));
              const label = topicLabel("theme", topic);
              const muted = color.includes("muted");
              return (
                <Link key={topic.key} href={radarHref(radar.window.kind, radar.window.key, { ...view, focus })} scroll={false} aria-label={`${label} 현재 ${last(ranks)}위`}>
                  <g
                    data-tip={`${label}\n현재 ${last(ranks)}위 (${delta > 0 ? `▲${delta}` : delta < 0 ? `▼${-delta}` : "변동 없음"})\n${ranks.map((r, i) => `${periodLabel(radar.periods[i])} ${r ?? "-"}`).join(" · ")}`}
                    className="cursor-pointer [&:hover_polyline.line]:stroke-[3.5] [&:hover_polyline.line]:stroke-opacity-100"
                  >
                    {segments.map((points) => (
                      <g key={points}>
                        <polyline points={points} fill="none" stroke="transparent" strokeWidth={14} />
                        <polyline className="line" points={points} fill="none" stroke={color} strokeWidth={selected ? 3.5 : muted ? 1.5 : 2.5} strokeLinejoin="round" strokeLinecap="round" strokeOpacity={muted && !selected ? 0.4 : 1} />
                      </g>
                    ))}
                    {ranks.map((rank, i) =>
                      rank !== null && rank <= top ? (
                        <circle key={radar.periods[i]} cx={x(i)} cy={y(rank)} r={muted ? 3 : 4} fill={color} fillOpacity={muted && !selected ? 0.55 : 1} stroke="var(--card)" strokeWidth={2} />
                      ) : null,
                    )}
                    <text x={x(n - 1) + 10} y={y(last(ranks) ?? top) + 4} fontSize={12} fontWeight={selected ? 700 : 500} fill="var(--foreground)">
                      <tspan fill="var(--muted-foreground)" className="tabular-nums">{last(ranks)}  </tspan>
                      {label.length > 13 ? `${label.slice(0, 12)}…` : label}
                    </text>
                  </g>
                </Link>
              );
            })}
        </svg>
      </div>
      <Legend
        className="mt-1"
        items={[
          { label: "3계단 이상 상승", swatch: "var(--state-hot)" },
          { label: "3계단 이상 하락", swatch: "var(--state-cool)" },
          { label: "비슷", swatch: "var(--muted-foreground)" },
        ]}
      />
      <p className="mt-1 text-xs text-muted-foreground">선이 끊긴 곳은 그 기간에 상위 {top}위 밖이었다는 뜻입니다.</p>
    </ChartTips>
  );
}

// ── opportunity / risk balance ───────────────────────────────────────────────────────────

/** Diverging stacked bars: risk to the left, opportunity to the right, "watch" straddling zero. */
export function ImpactBalance({ radar, view, limit = 12 }: { radar: Radar; view: RadarView; limit?: number }) {
  const rows = radar.themes
    .filter((t) => t.impacts.opportunity + t.impacts.risk + t.impacts.watch >= 3)
    .sort((a, b) => last(b.counts) - last(a.counts))
    .slice(0, limit)
    .sort((a, b) => (netOpportunity(b) ?? 0) - (netOpportunity(a) ?? 0));
  if (!rows.length) return <p className="py-10 text-center text-sm text-muted-foreground">영향이 분류된 테마가 부족합니다.</p>;
  return (
    <ChartTips>
      <div className="mb-1 grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_3rem] gap-3 text-[11px] text-muted-foreground sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_3.5rem]">
        <span />
        <span className="flex justify-between">
          <span>← 위험</span>
          <span>기회 →</span>
        </span>
        <span className="text-right">순기회</span>
      </div>
      <ul className="space-y-1.5">
        {rows.map((theme) => {
          const { opportunity, risk, watch } = theme.impacts;
          const total = opportunity + risk + watch;
          const pct = (v: number) => (v / total) * 50; // each side spans half the bar
          const net = netOpportunity(theme) ?? 0;
          const focus = { kind: "theme" as const, key: theme.key };
          const label = topicLabel("theme", theme);
          return (
            <li key={theme.key} className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)_3rem] items-center gap-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_3.5rem]">
              <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus })} scroll={false} className={cn("truncate text-sm hover:text-primary", sameFocus(view.focus, focus) && "font-bold text-primary")}>
                {label}
              </Link>
              <span className="relative h-4" data-tip={`${label}\n순기회 ${net >= 0 ? "+" : "−"}${Math.abs(Math.round(net * 100))}\n기회 ${opportunity} · 관찰 ${watch} · 위험 ${risk}`}>
                <span className="absolute inset-y-0 left-1/2 w-px bg-border" aria-hidden />
                <span className="absolute inset-y-0 rounded-l-[4px] bg-impact-risk" style={{ right: `calc(50% + ${pct(watch / 2)}% + 1px)`, width: `${pct(risk)}%` }} />
                <span className="absolute inset-y-0 bg-impact-watch/60" style={{ left: `calc(50% - ${pct(watch / 2)}%)`, width: `${pct(watch)}%` }} />
                <span className="absolute inset-y-0 rounded-r-[4px] bg-impact-opportunity" style={{ left: `calc(50% + ${pct(watch / 2)}% + 1px)`, width: `${pct(opportunity)}%` }} />
              </span>
              <span className={cn("text-right text-xs font-semibold tabular-nums", net > 0.1 ? "text-impact-opportunity" : net < -0.1 ? "text-impact-risk" : "text-muted-foreground")}>
                {net >= 0 ? "+" : "−"}
                {Math.abs(Math.round(net * 100))}
              </span>
            </li>
          );
        })}
      </ul>
      <Legend
        className="mt-3"
        items={(["risk", "watch", "opportunity"] as const).map((impact) => ({ label: IMPACT_LABEL[impact], swatch: `var(--impact-${impact})` }))}
      />
    </ChartTips>
  );
}

// ── propagation flows ────────────────────────────────────────────────────────────────────

export function formatLag(hours: number): string {
  if (hours < 1) return "1시간 안";
  if (hours < 48) return `${Math.round(hours)}시간`;
  return `${(hours / 24).toFixed(1)}일`;
}

/** Bipartite flow: which track picked a subject up first (left) and which followed (right). */
export function FlowDiagram({ radar }: { radar: Radar }) {
  const { links, chains, origins } = radar.flows;
  if (!links.length) {
    return <p className="py-10 text-center text-sm text-muted-foreground">이번 기간에 트랙을 건너간 이슈·식별자 연결이 없습니다.</p>;
  }
  const W = 620, H = 316, NODE = 12, GAP = 14, L = 92, R = 92, CAPTION = 18;
  const outTotal = (t: Track) => links.filter((l) => l.source === t).reduce((s, l) => s + l.count, 0);
  const inTotal = (t: Track) => links.filter((l) => l.target === t).reduce((s, l) => s + l.count, 0);
  const total = links.reduce((s, l) => s + l.count, 0);
  const scale = (H - CAPTION - GAP * 3) / total;
  const column = (size: (t: Track) => number) => {
    let y = 0;
    return new Map(
      PIPELINE.map((t) => {
        const h = size(t) * scale;
        const box = { y, h };
        y += h + (h ? GAP : 0);
        return [t, box];
      }),
    );
  };
  const left = column(outTotal), right = column(inTotal);
  const leftCursor = new Map(PIPELINE.map((t) => [t, left.get(t)!.y]));
  const rightCursor = new Map(PIPELINE.map((t) => [t, right.get(t)!.y]));
  const ordered = [...links].sort((a, b) => PIPELINE.indexOf(a.source) - PIPELINE.indexOf(b.source) || PIPELINE.indexOf(a.target) - PIPELINE.indexOf(b.target));
  const x0 = L + NODE, x1 = W - R - NODE, mid = (x0 + x1) / 2;
  const fastest = [...links].filter((l) => l.count >= 2).sort((a, b) => a.median_hours - b.median_hours)[0];
  return (
    <ChartTips>
      <p className="mb-2 text-xs text-ink-2">
        이번 기간 트랙을 건너간 주제 <b className="text-foreground tabular-nums">{chains}</b>개 · 처음 나온 곳{" "}
        {PIPELINE.filter((t) => origins[t]).map((t, i) => (
          <span key={t}>
            {i ? ", " : ""}
            {TRACK_LABEL[t]} <b className="text-foreground tabular-nums">{origins[t]}</b>
          </span>
        ))}
        {fastest ? ` · 가장 빠른 전파: ${TRACK_LABEL[fastest.source]}→${TRACK_LABEL[fastest.target]} ${formatLag(fastest.median_hours)}` : ""}
      </p>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[520px]" role="img" aria-label="먼저 다룬 트랙에서 다음 트랙으로 넘어간 주제 수와 걸린 시간">
          {ordered.map((link) => {
            const h = link.count * scale;
            const ys = leftCursor.get(link.source)!, yt = rightCursor.get(link.target)!;
            leftCursor.set(link.source, ys + h);
            rightCursor.set(link.target, yt + h);
            const path = `M${x0},${ys} C${mid},${ys} ${mid},${yt} ${x1},${yt} L${x1},${yt + h} C${mid},${yt + h} ${mid},${ys + h} ${x0},${ys + h} Z`;
            return (
              <path
                key={`${link.source}-${link.target}`}
                d={path}
                fill={TRACK_FILL[link.source]}
                fillOpacity={0.32}
                stroke="var(--card)"
                strokeWidth={1}
                className="transition-[fill-opacity] hover:fill-opacity-60"
                data-tip={`${TRACK_LABEL[link.source]} → ${TRACK_LABEL[link.target]}\n${link.count}건\n중앙값 ${formatLag(link.median_hours)} 뒤`}
              />
            );
          })}
          {PIPELINE.map((t) => {
            const a = left.get(t)!, b = right.get(t)!;
            return (
              <g key={t}>
                {a.h ? (
                  <>
                    <rect x={L} y={a.y} width={NODE} height={a.h} rx={3} fill={TRACK_FILL[t]} data-tip={`먼저: ${TRACK_LABEL[t]}\n${outTotal(t)}건`} />
                    <text x={L - 6} y={a.y + a.h / 2 + 4} fontSize={11.5} textAnchor="end" fill="var(--foreground)">{TRACK_LABEL[t]}</text>
                  </>
                ) : null}
                {b.h ? (
                  <>
                    <rect x={W - R - NODE} y={b.y} width={NODE} height={b.h} rx={3} fill={TRACK_FILL[t]} data-tip={`다음: ${TRACK_LABEL[t]}\n${inTotal(t)}건`} />
                    <text x={W - R + 6} y={b.y + b.h / 2 + 4} fontSize={11.5} fill="var(--foreground)">{TRACK_LABEL[t]}</text>
                  </>
                ) : null}
              </g>
            );
          })}
          <text x={L + NODE / 2} y={H - 2} fontSize={10.5} textAnchor="middle" fill="var(--muted-foreground)">먼저</text>
          <text x={W - R - NODE / 2} y={H - 2} fontSize={10.5} textAnchor="middle" fill="var(--muted-foreground)">다음</text>
        </svg>
      </div>
      <table className="mt-3 w-full text-sm">
        <caption className="sr-only">트랙 간 전파 경로</caption>
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th className="py-1.5 font-medium">경로</th>
            <th className="py-1.5 text-right font-medium">건수</th>
            <th className="py-1.5 text-right font-medium">걸린 시간 (중앙값)</th>
          </tr>
        </thead>
        <tbody>
          {links.slice(0, 6).map((link) => (
            <tr key={`${link.source}-${link.target}`} className="border-b last:border-0">
              <td className="py-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: TRACK_FILL[link.source] }} aria-hidden />
                  {TRACK_LABEL[link.source]} → {TRACK_LABEL[link.target]}
                </span>
              </td>
              <td className="py-1.5 text-right tabular-nums">{link.count}</td>
              <td className="py-1.5 text-right text-ink-2 tabular-nums">{formatLag(link.median_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ChartTips>
  );
}
