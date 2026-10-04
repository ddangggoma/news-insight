import Link from "next/link";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { Legend } from "@/components/reader/radar/parts";
import { formatNumber, TRACK_LABEL } from "@/lib/format";
import { last, radarHref, type RadarView, sameFocus, topicLabel } from "@/lib/radar";
import type { Radar } from "@/lib/reader-types";
import { FIELD_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const METRIC_LABEL: Record<string, string> = {
  stars: "★ 스타",
  points: "▲ 포인트",
  likes: "♥ 좋아요",
  reactions: "반응",
  score: "점수",
  comments: "댓글",
  downloads: "다운로드",
  answers: "답변",
};

// ── reactions vs coverage ────────────────────────────────────────────────────────────────

/**
 * Each theme's share of all mentions (x) against its share of all reaction growth (y). On the
 * diagonal the two agree; above it developers react more than the press writes (bottom-up
 * adoption), below it coverage runs ahead of any measurable pull.
 */
export function EngagementMatrix({ radar, view }: { radar: Radar; view: RadarView }) {
  const scores = new Map(radar.engagement.themes.map((t) => [t.key, t]));
  const themes = radar.themes.filter((t) => last(t.counts) >= 3 || scores.has(t.key));
  const mentions = themes.reduce((sum, t) => sum + last(t.counts), 0);
  const reactions = radar.engagement.themes.reduce((sum, t) => sum + t.score, 0);
  if (!mentions || !reactions) {
    return <p className="py-16 text-center text-sm text-muted-foreground">이번 기간에 스타·포인트 같은 반응 지표가 늘어난 항목이 없습니다.</p>;
  }
  const points = themes.map((t) => ({ topic: t, x: last(t.counts) / mentions, y: (scores.get(t.key)?.score ?? 0) / reactions, items: scores.get(t.key)?.items ?? 0 }));
  const W = 560, H = 360, L = 44, R = 14, T = 14, B = 34;
  const max = Math.max(...points.flatMap((p) => [p.x, p.y]), 0.05);
  const top = Math.ceil(max * 20) / 20; // round up to 5 %
  const sx = (v: number) => L + Math.sqrt(v / top) * (W - L - R);
  const sy = (v: number) => H - B - Math.sqrt(v / top) * (H - T - B);
  const ticks = [0, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5].filter((v) => v <= top);
  const lean = (p: (typeof points)[number]) => (p.y >= p.x * 1.6 && p.y >= 0.02 && p.items >= 3 ? "pull" : p.x >= p.y * 1.6 && p.x >= 0.02 ? "press" : "even");
  const fill = { pull: "var(--viz-oss)", press: "var(--viz-news)", even: "var(--muted-foreground)" } as const;
  // the biggest themes and the ones furthest from the line
  const off = (p: (typeof points)[number]) => Math.abs(Math.log((p.y + 0.002) / (p.x + 0.002))) * (p.x + p.y);
  const labelled = new Set([
    ...[...points].sort((a, b) => b.x + b.y - (a.x + a.y)).slice(0, 4),
    ...[...points].sort((a, b) => off(b) - off(a)).slice(0, 7),
  ].map((p) => p.topic.key));
  const placed: { x: number; y: number; w: number }[] = [];
  return (
    <ChartTips>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="테마별 언급 비중과 반응 증가 비중">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={sx(v)} x2={sx(v)} y1={T} y2={H - B} stroke="var(--border)" />
            <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} stroke="var(--border)" />
            <text x={sx(v)} y={H - B + 15} fontSize={11} textAnchor="middle" fill="var(--muted-foreground)">{Math.round(v * 100)}%</text>
            <text x={L - 6} y={sy(v) + 4} fontSize={11} textAnchor="end" fill="var(--muted-foreground)">{Math.round(v * 100)}%</text>
          </g>
        ))}
        <line x1={sx(0)} y1={sy(0)} x2={sx(top)} y2={sy(top)} stroke="var(--muted-foreground)" strokeOpacity={0.7} />
        <text x={L + 8} y={T + 28} fontSize={12} fontWeight={700} fill="var(--ink-2)" opacity={0.75}>반응 &gt; 보도</text>
        <text x={W - R - 8} y={H - B - 24} fontSize={12} fontWeight={700} textAnchor="end" fill="var(--ink-2)" opacity={0.75}>보도 &gt; 반응</text>
        <text x={W - R} y={H - 4} fontSize={11} textAnchor="end" fill="var(--muted-foreground)">언급 비중 →</text>
        <text x={L + 4} y={T + 10} fontSize={11} fill="var(--muted-foreground)">↑ 반응 증가 비중</text>
        {points.map((p) => {
          const focus = { kind: "theme" as const, key: p.topic.key };
          const r = 5 + Math.min(Math.sqrt(p.items) * 1.6, 9);
          return (
            <Link key={p.topic.key} href={radarHref(radar.window.kind, radar.window.key, { ...view, focus })} scroll={false} aria-label={topicLabel("theme", p.topic)}>
              <g data-tip={`${topicLabel("theme", p.topic)}\n반응 ${Math.round(p.y * 100)}% · 언급 ${Math.round(p.x * 100)}%\n언급 ${last(p.topic.counts)}건 · 반응이 늘어난 항목 ${p.items}건`} className="cursor-pointer">
                <circle cx={sx(p.x)} cy={sy(p.y)} r={Math.max(r + 4, 12)} fill="transparent" />
                <circle cx={sx(p.x)} cy={sy(p.y)} r={r} fill={fill[lean(p)]} fillOpacity={0.85} stroke={sameFocus(view.focus, focus) ? "var(--foreground)" : "var(--card)"} strokeWidth={2} />
              </g>
            </Link>
          );
        })}
        {points
          .filter((p) => labelled.has(p.topic.key))
          .map((p) => {
            const label = topicLabel("theme", p.topic);
            const w = label.length * 10.5;
            let x = sx(p.x) + 12, y = sy(p.y) + 4;
            const clash = () => x < L || x + w > W - R || placed.some((o) => Math.abs(o.y - y) < 13 && x < o.x + o.w && o.x < x + w);
            if (clash()) x = sx(p.x) - 12 - w;
            if (clash()) y -= 14;
            if (clash()) return null;
            placed.push({ x, y, w });
            return (
              <text key={p.topic.key} x={x} y={y} fontSize={11.5} fontWeight={600} fill="var(--foreground)" paintOrder="stroke" stroke="var(--card)" strokeWidth={3} className="pointer-events-none">
                {label}
              </text>
            );
          })}
      </svg>
      <Legend
        className="mt-1"
        items={[
          { label: "반응이 보도보다 큼 (1.6배 이상)", swatch: fill.pull, shape: "dot" },
          { label: "보도가 반응보다 큼", swatch: fill.press, shape: "dot" },
          { label: "비슷", swatch: fill.even, shape: "dot" },
        ]}
      />
    </ChartTips>
  );
}

export function TopMovers({ radar }: { radar: Radar }) {
  const { top, measured } = radar.engagement;
  if (!top.length) return null;
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold text-muted-foreground">반응 급등 항목 · 이번 기간 증가량 (측정 {formatNumber(measured)}건)</h3>
      <ol className="space-y-1.5">
        {top.map((item, i) => (
          <li key={item.id}>
            <Link href={`/items/${item.id}`} className="flex items-center gap-3 rounded-xl border px-3 py-2 text-sm transition hover:border-primary/40 hover:bg-muted/40">
              <span className="w-4 text-xs text-muted-foreground tabular-nums">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{item.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {TRACK_LABEL[item.track]} · {item.source_name}
                </span>
              </span>
              <span className="text-right text-xs whitespace-nowrap">
                <b className="block text-sm text-foreground tabular-nums">+{formatNumber(item.gain)}</b>
                <span className="text-muted-foreground">{METRIC_LABEL[item.metric] ?? item.metric} · 총 {formatNumber(item.current)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── calendar heatmap ─────────────────────────────────────────────────────────────────────

const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"];

function isoDay(start: string, offset: number): string {
  const [y, m, d] = start.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + offset)).toISOString().slice(0, 10);
}

/** Reports per day, weeks as columns; outlined days had one category far above its usual level. */
export function ActivityCalendar({ radar, view }: { radar: Radar; view: RadarView }) {
  const { start, days, anomalies } = radar.calendar;
  if (!days.length) return null;
  const [y, m, d] = start.split("-").map(Number);
  const offset = (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; // Monday = 0
  const weeks = Math.ceil((days.length + offset) / 7);
  const CELL = 14, GAP = 3, L = 22, T = 18, R = 14;
  const W = L + weeks * (CELL + GAP) + R, H = T + 7 * (CELL + GAP);
  const sorted = [...days].filter((v) => v > 0).sort((a, b) => a - b);
  const cut = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] ?? 0;
  const steps = [cut(0.2), cut(0.4), cut(0.6), cut(0.8)];
  const level = (v: number) => (v === 0 ? 0 : 1 + steps.filter((s) => v > s).length);
  const fill = (lvl: number) => (lvl === 0 ? "var(--muted)" : `color-mix(in oklab, var(--heat) ${[0, 18, 34, 52, 70, 88][lvl]}%, var(--muted))`);
  const byDay = new Map<string, typeof anomalies>();
  for (const a of anomalies) byDay.set(a.day, [...(byDay.get(a.day) ?? []), a]);
  const windowStart = radar.window.start.slice(0, 10);
  const months: { x: number; label: string }[] = [];
  days.forEach((_, i) => {
    const iso = isoDay(start, i);
    if (iso.endsWith("-01") || i === 0) months.push({ x: L + Math.floor((i + offset) / 7) * (CELL + GAP), label: `${Number(iso.slice(5, 7))}월` });
  });
  return (
    <ChartTips className="grid gap-5 xl:grid-cols-[auto_minmax(0,1fr)] [&>*]:min-w-0">
      <div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" style={{ minWidth: Math.min(W, 640), maxWidth: Math.max(W * 1.6, 420) }} role="img" aria-label="일별 보도량 캘린더">
          {months.map((month) => (
            <text key={`${month.x}-${month.label}`} x={month.x} y={11} fontSize={10} fill="var(--muted-foreground)">{month.label}</text>
          ))}
          {WEEKDAYS.map((label, row) =>
            row % 2 === 0 ? (
              <text key={label} x={0} y={T + row * (CELL + GAP) + CELL - 3} fontSize={10} fill="var(--muted-foreground)">{label}</text>
            ) : null,
          )}
          {days.map((count, i) => {
            const iso = isoDay(start, i);
            const col = Math.floor((i + offset) / 7), row = (i + offset) % 7;
            const marks = byDay.get(iso);
            const tip = [
              `${iso} (${WEEKDAYS[row]})`,
              `${count}건`,
              ...(marks ?? []).map((a) => `${FIELD_LABEL[a.field] ?? a.field} ${a.count}건 (평소 ${a.expected.toFixed(1)}): ${a.keywords.map((k) => k.label).join(", ")}`),
            ].join("\n");
            return (
              <rect
                key={iso}
                x={L + col * (CELL + GAP)}
                y={T + row * (CELL + GAP)}
                width={CELL}
                height={CELL}
                rx={3}
                fill={fill(level(count))}
                opacity={iso < windowStart ? 0.6 : 1}
                stroke={marks ? "var(--foreground)" : "none"}
                strokeWidth={marks ? 2 : 0}
                data-tip={tip}
              />
            );
          })}
        </svg>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1" aria-hidden>
          적음
          {[1, 2, 3, 4, 5].map((lvl) => (
            <span key={lvl} className="size-3 rounded-[3px]" style={{ background: fill(lvl) }} />
          ))}
          많음
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-3 rounded-[3px] border-2 border-foreground" aria-hidden /> 이례적인 날
        </span>
        <span>흐린 칸 = 이번 기간 이전</span>
      </div>
      </div>
      {anomalies.length ? (
        <ul className="space-y-1.5 self-start">
          {[...anomalies].reverse().map((a) => (
            <li key={`${a.day}-${a.field}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-muted/60 px-2.5 py-1.5 text-sm">
              <span className="font-semibold tabular-nums">{a.day.slice(5).replace("-", "/")}</span>
              <span>{FIELD_LABEL[a.field] ?? a.field}</span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {a.count}건 · 평소의 {(a.count / Math.max(a.expected, 1)).toFixed(1)}배
              </span>
              <span className="flex flex-wrap gap-1">
                {a.keywords.map((k) => (
                  <Link
                    key={k.key}
                    href={radarHref(radar.window.kind, radar.window.key, { ...view, focus: { kind: "keyword", key: k.key } })}
                    scroll={false}
                    className="rounded-full border bg-background px-2 text-xs text-ink-2 hover:border-primary hover:text-primary"
                  >
                    {k.label}
                  </Link>
                ))}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">평소보다 눈에 띄게 많았던 날이 없습니다.</p>
      )}
    </ChartTips>
  );
}

// ── cross-category matrix ────────────────────────────────────────────────────────────────

/** Reports classified into two categories: where fields meet, and which meetings are new. */
export function FieldCrossMatrix({ radar, view }: { radar: Radar; view: RadarView }) {
  const links = radar.field_links;
  if (!links.length) return <p className="py-10 text-center text-sm text-muted-foreground">두 카테고리에 함께 분류된 보도가 없습니다.</p>;
  const weight = new Map<string, number>();
  for (const l of links) for (const f of [l.a, l.b]) weight.set(f, (weight.get(f) ?? 0) + l.count);
  const fields = [...weight.keys()].sort((a, b) => (weight.get(b) ?? 0) - (weight.get(a) ?? 0)).slice(0, 10);
  const cell = new Map(links.map((l) => [`${l.a}|${l.b}`, l]));
  const at = (a: string, b: string) => cell.get(a < b ? `${a}|${b}` : `${b}|${a}`);
  const max = Math.max(...links.map((l) => l.count));
  const short = (key: string) => (FIELD_LABEL[key] ?? key).split("·")[0];
  return (
    <ChartTips>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] [&>*]:min-w-0">
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-[2px] text-xs">
            <caption className="sr-only">카테고리 쌍별로 두 카테고리에 함께 분류된 보도 수</caption>
            <tbody>
              {fields.slice(1).map((row, r) => (
                <tr key={row}>
                  <th scope="row" className="pr-2 text-right font-medium whitespace-nowrap">
                    <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus: { kind: "field", key: row } })} scroll={false} className="hover:text-primary">
                      {short(row)}
                    </Link>
                  </th>
                  {fields.slice(0, r + 1).map((col) => {
                    const link = at(row, col);
                    const level = link ? Math.max(14, Math.round(Math.sqrt(link.count / max) * 85)) : 0;
                    const fresh = !!link && link.previous === 0;
                    return (
                      <td
                        key={col}
                        data-tip={link ? `${FIELD_LABEL[row]} × ${FIELD_LABEL[col]}\n${link.count}건\n직전 기간 ${link.previous}건${fresh ? " · 새로 생긴 교차" : ""}` : `${FIELD_LABEL[row]} × ${FIELD_LABEL[col]}\n0건`}
                        className={cn("relative size-9 rounded-[5px] text-center tabular-nums", level >= 55 ? "font-semibold text-heat-ink" : "text-ink-2")}
                        style={{ background: link ? `color-mix(in oklab, var(--heat) ${level}%, var(--muted))` : "var(--muted)" }}
                      >
                        {link?.count ?? ""}
                        {fresh ? <span className="absolute top-0.5 right-0.5 size-1.5 rounded-full bg-primary" aria-label="새로 생긴 교차" /> : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <td />
                {fields.slice(0, -1).map((col) => (
                  <th key={col} scope="col" className="h-20 align-top font-medium">
                    <span className="inline-block origin-top-left translate-x-3 rotate-45 whitespace-nowrap">{short(col)}</span>
                  </th>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <ol className="space-y-1.5 text-sm">
          {links.slice(0, 8).map((l) => {
            const delta = l.count - l.previous;
            return (
              <li key={`${l.a}-${l.b}`} className="flex items-center gap-2 rounded-lg bg-muted/60 px-2.5 py-1.5">
                <span className="min-w-0 flex-1 truncate">
                  {FIELD_LABEL[l.a]} <span className="text-muted-foreground">×</span> {FIELD_LABEL[l.b]}
                </span>
                {l.previous === 0 ? <span className="rounded-full bg-primary/12 px-1.5 text-[11px] font-semibold text-primary">신규</span> : null}
                <span className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
                  {l.count}건 ({delta >= 0 ? "+" : "−"}
                  {Math.abs(delta)})
                </span>
              </li>
            );
          })}
        </ol>
      </div>
      <Legend className="mt-3" items={[{ label: "이번 기간 처음 생긴 교차", swatch: "var(--primary)", shape: "dot" }]} />
    </ChartTips>
  );
}
