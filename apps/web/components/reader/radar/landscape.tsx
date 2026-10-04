import Link from "next/link";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { Legend, StateBadge } from "@/components/reader/radar/parts";
import {
  type Focus,
  formatChange,
  formatZ,
  last,
  MOMENTUM_Z,
  periodLabel,
  QUADRANT_META,
  quadrantOf,
  radarHref,
  type RadarView,
  type Rect,
  researchShare,
  sameFocus,
  squarify,
  STAGE_META,
  stageOf,
  STATE_META,
  topicLabel,
  volumeSplit,
  zLevel,
} from "@/lib/radar";
import type { Radar, Topic } from "@/lib/reader-types";
import { FIELD_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

function focusHref(radar: Radar, view: RadarView, focus: Focus): string {
  return radarHref(radar.window.kind, radar.window.key, { ...view, focus });
}

function topicTip(kind: "field" | "theme", topic: Topic, radar: Radar): string {
  const share = researchShare(topic.tracks);
  return [
    kind === "theme" && topic.field ? `${FIELD_LABEL[topic.field]} › ${topicLabel(kind, topic)}` : topicLabel(kind, topic),
    `${last(topic.counts)}건 · ${formatZ(topic.z)}`,
    `직전 ${periodLabel(radar.periods[radar.periods.length - 2])} 대비 ${formatChange(topic.change)} · 출처 ${topic.sources}곳`,
    topic.state ? `상태: ${STATE_META[topic.state].label}` : "",
    share !== null ? `논문·오픈소스 ${Math.round(share * 100)}%` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

/** Diverging momentum fill: heat for z > 0, cool for z < 0, the muted surface at 0. */
export function momentumFill(z: number): string {
  const level = zLevel(z);
  return `color-mix(in oklab, var(${z >= 0 ? "--heat" : "--cool"}) ${level}%, var(--muted))`;
}

type Box = Topic & Rect & { themes: (Topic & Rect & { value: number })[]; header: boolean };

function layout(radar: Radar, width: number, height: number): Box[] {
  const fields = radar.fields.filter((f) => last(f.counts) > 0).map((f) => ({ ...f, value: last(f.counts) }));
  return squarify(fields, { x: 0, y: 0, w: width, h: height }).map((box) => {
    const header = box.h > 56 && box.w > 84;
    const inner = { x: box.x + 2, y: box.y + (header ? 22 : 2), w: box.w - 4, h: box.h - (header ? 24 : 4) };
    const themes = radar.themes.filter((t) => t.field === box.key && last(t.counts) > 0).map((t) => ({ ...t, value: last(t.counts) }));
    return { ...box, header, themes: squarify(themes, inner) };
  });
}

function TreemapLayer({ radar, view, width, height, className }: { radar: Radar; view: RadarView; width: number; height: number; className?: string }) {
  const boxes = layout(radar, width, height);
  const pct = (value: number, of: number) => `${(value / of) * 100}%`;
  const place = (r: Rect) => ({ left: pct(r.x, width), top: pct(r.y, height), width: pct(r.w, width), height: pct(r.h, height) });
  return (
    <div className={cn("relative w-full", className)} style={{ aspectRatio: `${width} / ${height}` }}>
      {boxes.map((box) => (
        <div key={box.key} className="absolute p-px" style={place(box)}>
          <div className="relative size-full overflow-hidden rounded-lg bg-muted/60 ring-1 ring-border">
            {box.header ? (
              <Link
                href={focusHref(radar, view, { kind: "field", key: box.key })}
                scroll={false}
                data-tip={topicTip("field", box, radar)}
                className={cn(
                  "absolute inset-x-0 top-0 flex h-[22px] items-center justify-between gap-1 px-2 text-[11px] font-bold text-ink-2 hover:text-primary",
                  sameFocus(view.focus, { kind: "field", key: box.key }) && "text-primary",
                )}
              >
                <span className="truncate">{FIELD_LABEL[box.key]}</span>
                <span className="font-medium tabular-nums">{last(box.counts)}</span>
              </Link>
            ) : null}
          </div>
          {box.themes.map((theme) => {
            const level = zLevel(theme.z);
            const focus = { kind: "theme" as const, key: theme.key };
            const big = theme.w > 76 && theme.h > 42;
            return (
              <Link
                key={theme.key}
                href={focusHref(radar, view, focus)}
                scroll={false}
                data-tip={topicTip("theme", theme, radar)}
                aria-label={`${topicLabel("theme", theme)} ${last(theme.counts)}건, ${formatZ(theme.z)}`}
                aria-current={sameFocus(view.focus, focus) ? "true" : undefined}
                className={cn(
                  "absolute flex flex-col justify-between overflow-hidden rounded-md p-1.5 text-left leading-tight transition-[filter,outline] hover:brightness-105 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-ring",
                  level >= 45 ? "text-heat-ink" : "text-foreground",
                  sameFocus(view.focus, focus) && "z-10 outline-2 outline-offset-1 outline-foreground",
                )}
                style={{
                  left: pct(theme.x - box.x + 1, box.w),
                  top: pct(theme.y - box.y + 1, box.h),
                  width: `calc(${pct(theme.w, box.w)} - 2px)`,
                  height: `calc(${pct(theme.h, box.h)} - 2px)`,
                  background: momentumFill(theme.z),
                }}
              >
                {big ? (
                  <>
                    <span className="line-clamp-2 text-xs font-semibold">{topicLabel("theme", theme)}</span>
                    <span className="flex items-baseline justify-between gap-1 text-[11px] tabular-nums">
                      <span className="font-bold">{last(theme.counts)}</span>
                      <span className="opacity-80">{formatZ(theme.z)}</span>
                    </span>
                  </>
                ) : theme.w > 60 && theme.h > 22 ? (
                  <span className="truncate text-[10px] font-semibold">{topicLabel("theme", theme)}</span>
                ) : null}
              </Link>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function CategoryTreemap({ radar, view }: { radar: Radar; view: RadarView }) {
  if (!radar.themes.some((t) => last(t.counts) > 0)) {
    return <p className="py-16 text-center text-sm text-muted-foreground">이 기간에 분류된 기사가 없습니다.</p>;
  }
  return (
    <ChartTips>
      <TreemapLayer radar={radar} view={view} width={1000} height={500} className="hidden md:block" />
      <TreemapLayer radar={radar} view={view} width={400} height={560} className="md:hidden" />
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>면적 = 이번 기간 언급량 · 색 = 직전 기간 평균 대비 모멘텀(z)</span>
        <span className="ml-auto flex items-center gap-1.5" aria-hidden>
          <span>하락</span>
          {[-3, -1.5, 0, 1.5, 3].map((z) => (
            <span key={z} className="h-3 w-6 rounded-sm" style={{ background: momentumFill(z) }} />
          ))}
          <span>급상승</span>
        </span>
      </div>
    </ChartTips>
  );
}

// ── positioning matrix ───────────────────────────────────────────────────────────────────

const STAGE_FILL = { research: "var(--stage-research)", diffusion: "var(--stage-diffusion)", market: "var(--stage-market)" } as const;

/** Themes by attention (x, log) and momentum (y, z-score); quadrants say what to do now. */
export function PositioningMatrix({ radar, view }: { radar: Radar; view: RadarView }) {
  if (radar.themes.filter((t) => last(t.counts) > 0).length < 2) {
    return <p className="py-16 text-center text-sm text-muted-foreground">비교할 테마가 부족합니다.</p>;
  }
  return (
    <ChartTips>
      <MatrixChart radar={radar} view={view} W={720} H={400} labelCount={12} className="hidden sm:block" />
      <MatrixChart radar={radar} view={view} W={380} H={360} labelCount={6} className="sm:hidden" />
      <Legend
        className="mt-2"
        items={(Object.keys(STAGE_META) as (keyof typeof STAGE_META)[]).map((stage) => ({ label: `${STAGE_META[stage].label}`, swatch: STAGE_FILL[stage], shape: "dot" }))}
      />
    </ChartTips>
  );
}

function MatrixChart({ radar, view, W, H, labelCount, className }: { radar: Radar; view: RadarView; W: number; H: number; labelCount: number; className: string }) {
  const points = radar.themes.filter((t) => last(t.counts) > 0);
  const L = 40, R = 14, T = 14, B = 34;
  const split = volumeSplit(points);
  const maxCount = Math.max(...points.map((p) => last(p.counts)), split * 2);
  const zs = points.map((p) => p.z);
  const y0 = Math.min(-2, Math.floor(Math.min(...zs))), y1 = Math.max(3, Math.min(8, Math.ceil(Math.max(...zs))));
  const sx = (count: number) => L + (Math.log(count) / Math.log(maxCount)) * (W - L - R);
  const sy = (z: number) => T + ((y1 - Math.max(y0, Math.min(y1, z))) / (y1 - y0)) * (H - T - B);
  const xTicks = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].filter((v) => v <= maxCount);
  const yTicks = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i).filter((v) => (y1 - y0 > 6 ? v % 2 === 0 : true));
  const radius = (sources: number) => Math.min(18, 5 + Math.sqrt(sources) * 2.2);
  const ranked = [...points].sort((a, b) => b.z * Math.log(last(b.counts) + 1) - a.z * Math.log(last(a.counts) + 1));
  const labelled = new Set(ranked.slice(0, labelCount).map((p) => p.key));
  const placed: { x: number; y: number; w: number }[] = [];
  const corner = [
    { q: "emerging" as const, x: L + 8, y: T + 16, anchor: "start" as const },
    { q: "leading" as const, x: W - R - 8, y: T + 16, anchor: "end" as const },
    { q: "niche" as const, x: L + 8, y: H - B - 8, anchor: "start" as const },
    { q: "mainstream" as const, x: W - R - 8, y: H - B - 8, anchor: "end" as const },
  ];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("h-auto w-full", className)} role="img" aria-label="테마별 언급량(가로, 로그)과 모멘텀(세로, z)">
        <rect x={sx(split)} y={T} width={W - R - sx(split)} height={sy(MOMENTUM_Z) - T} fill="var(--heat)" opacity={0.07} />
        <rect x={L} y={T} width={sx(split) - L} height={sy(MOMENTUM_Z) - T} fill="var(--primary)" opacity={0.06} />
        {xTicks.map((v) => (
          <g key={`x${v}`}>
            <line x1={sx(v)} x2={sx(v)} y1={T} y2={H - B} stroke="var(--border)" />
            <text x={sx(v)} y={H - B + 15} fontSize={11} textAnchor="middle" fill="var(--muted-foreground)">{v}</text>
          </g>
        ))}
        {yTicks.map((v) => (
          <g key={`y${v}`}>
            <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} stroke="var(--border)" />
            <text x={L - 6} y={sy(v) + 4} fontSize={11} textAnchor="end" fill="var(--muted-foreground)">{v > 0 ? `+${v}` : v}σ</text>
          </g>
        ))}
        <line x1={sx(split)} x2={sx(split)} y1={T} y2={H - B} stroke="var(--muted-foreground)" strokeOpacity={0.6} />
        <line x1={L} x2={W - R} y1={sy(MOMENTUM_Z)} y2={sy(MOMENTUM_Z)} stroke="var(--muted-foreground)" strokeOpacity={0.6} />
        <text x={W - R} y={H - 4} fontSize={11} textAnchor="end" fill="var(--muted-foreground)">이번 기간 언급량 (로그) →</text>
        {corner.map((c) => (
          <text key={c.q} x={c.x} y={c.y} fontSize={12} fontWeight={700} textAnchor={c.anchor} fill="var(--ink-2)" opacity={0.75}>
            {QUADRANT_META[c.q].label}
          </text>
        ))}
        {[...points]
          .sort((a, b) => b.sources - a.sources)
          .map((point) => {
            const cx = sx(last(point.counts)), cy = sy(point.z), r = radius(point.sources);
            const stage = stageOf(researchShare(point.tracks)) ?? "market";
            const focus = { kind: "theme" as const, key: point.key };
            const selected = sameFocus(view.focus, focus);
            return (
              <Link key={point.key} href={focusHref(radar, view, focus)} scroll={false} aria-label={`${topicLabel("theme", point)}: ${QUADRANT_META[quadrantOf(point, split)].label}`}>
                <g data-tip={`${topicTip("theme", point, radar)}\n${QUADRANT_META[quadrantOf(point, split)].label} · ${STAGE_META[stage].label}`} className="cursor-pointer [&:hover>circle.dot]:stroke-foreground">
                  <circle cx={cx} cy={cy} r={Math.max(r + 4, 12)} fill="transparent" />
                  <circle className="dot" cx={cx} cy={cy} r={r} fill={STAGE_FILL[stage]} fillOpacity={0.88} stroke={selected ? "var(--foreground)" : "var(--card)"} strokeWidth={2} />
                </g>
              </Link>
            );
          })}
        {ranked
          .filter((p) => labelled.has(p.key))
          .map((point) => {
            const cx = sx(last(point.counts)), cy = sy(point.z), r = radius(point.sources);
            const label = topicLabel("theme", point);
            const width = label.length * 10.5;
            const clashes = (x: number, y: number) => x < L || x + width > W - R || y < T + 10 || placed.some((o) => Math.abs(o.y - y) < 13 && x < o.x + o.w && o.x < x + width);
            let lx = cx + r + 4, ly = cy + 4;
            if (clashes(lx, ly)) lx = cx - r - 4 - width;
            if (clashes(lx, ly)) ly = cy - r - 4;
            if (clashes(lx, ly)) return null;
            placed.push({ x: lx, y: ly, w: width });
            return (
              <text key={point.key} x={lx} y={ly} fontSize={11.5} fontWeight={600} fill="var(--foreground)" className="pointer-events-none" paintOrder="stroke" stroke="var(--card)" strokeWidth={3}>
                {label}
              </text>
            );
          })}
    </svg>
  );
}

// ── timing heatmap ───────────────────────────────────────────────────────────────────────

/** Theme × period, each row scaled to its own peak so the timing of every theme is visible. */
export function TimingHeatmap({ radar, view, limit = 16 }: { radar: Radar; view: RadarView; limit?: number }) {
  const rows = radar.themes
    .filter((t) => t.counts.some((c) => c > 0))
    .sort((a, b) => b.z - a.z || last(b.counts) - last(a.counts))
    .slice(0, limit);
  if (!rows.length) return <p className="py-16 text-center text-sm text-muted-foreground">표시할 테마가 없습니다.</p>;
  return (
    <ChartTips>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-separate border-spacing-[2px] text-xs">
          <caption className="sr-only">테마별 기간별 언급량. 각 행은 그 테마의 최고치를 기준으로 칠합니다.</caption>
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col" className="pb-1 text-left font-medium">테마</th>
              {radar.periods.map((period, i) => (
                <th key={period} scope="col" className={cn("pb-1 font-medium tabular-nums", i === radar.periods.length - 1 && "text-foreground")}>
                  {periodLabel(period)}
                </th>
              ))}
              <th scope="col" className="pb-1 pl-2 text-right font-medium">모멘텀</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((theme) => {
              const peak = Math.max(...theme.counts, 1);
              const focus = { kind: "theme" as const, key: theme.key };
              return (
                <tr key={theme.key}>
                  <th scope="row" className="max-w-44 pr-2 text-left font-medium">
                    <Link
                      href={focusHref(radar, view, focus)}
                      scroll={false}
                      className={cn("block truncate hover:text-primary", sameFocus(view.focus, focus) && "font-bold text-primary")}
                      title={theme.field ? `${FIELD_LABEL[theme.field]} › ${topicLabel("theme", theme)}` : undefined}
                    >
                      {topicLabel("theme", theme)}
                    </Link>
                  </th>
                  {theme.counts.map((count, i) => {
                    const level = count ? Math.max(10, Math.round((count / peak) * 88)) : 0;
                    return (
                      <td
                        key={radar.periods[i]}
                        data-tip={`${topicLabel("theme", theme)} · ${radar.periods[i]}\n${count}건\n이 테마 최고치의 ${Math.round((count / peak) * 100)}%`}
                        aria-label={`${radar.periods[i]} ${count}건`}
                        className={cn("h-7 min-w-9 rounded-[5px] text-center tabular-nums", level >= 55 ? "font-semibold text-heat-ink" : "text-transparent")}
                        style={{ background: `color-mix(in oklab, var(--heat) ${level}%, var(--muted))` }}
                      >
                        {count || ""}
                      </td>
                    );
                  })}
                  <td className="pl-2 text-right whitespace-nowrap">
                    <span className="mr-1.5 tabular-nums text-ink-2">{formatZ(theme.z)}</span>
                    <StateBadge state={theme.state} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ChartTips>
  );
}
