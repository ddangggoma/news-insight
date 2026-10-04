import Link from "next/link";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { KeywordBadge, Legend, StateBadge } from "@/components/reader/radar/parts";
import { Sparkline } from "@/components/reader/sparkline";
import {
  type Focus,
  forceLayout,
  formatChange,
  formatZ,
  keywordIndex,
  last,
  mean,
  radarHref,
  type RadarView,
  researchShare,
  sameFocus,
  STATE_META,
  STATE_ORDER,
  textWidth,
  topicLabel,
  wordCloud,
} from "@/lib/radar";
import type { Radar, Topic, TopicState } from "@/lib/reader-types";
import { FIELD_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const STATE_FILL: Record<TopicState, string> = {
  new: "var(--primary)",
  surging: "var(--state-hot)",
  rising: "var(--state-hot)",
  steady: "var(--muted-foreground)",
  falling: "var(--state-cool)",
};

function keywordHref(radar: Radar, view: RadarView, key: string): string {
  return radarHref(radar.window.kind, radar.window.key, { ...view, focus: { kind: "keyword", key } });
}

function keywordTip(keyword: Topic): string {
  const share = researchShare(keyword.tracks);
  return [
    `${topicLabel("keyword", keyword)}${keyword.field ? ` · ${FIELD_LABEL[keyword.field] ?? keyword.field}` : ""}`,
    `${last(keyword.counts)}건 · ${formatZ(keyword.z)}`,
    `${keyword.state ? STATE_META[keyword.state].label : ""} · 직전 대비 ${formatChange(keyword.change)} · 출처 ${keyword.sources}곳`,
    share !== null ? `논문·오픈소스 ${Math.round(share * 100)}%` : "",
    keyword.returning ? "↺ 재등장" : keyword.debut ? "✦ 최근 첫 등장" : "",
  ]
    .filter(Boolean)
    .join("\n");
}

/** Technologies (card keywords): size = mentions this period, colour and weight = lifecycle. */
export function TechCloud({ radar, view }: { radar: Radar; view: RadarView }) {
  if (!radar.keywords.length) return <p className="py-16 text-center text-sm text-muted-foreground">이번 기간에 2번 이상 언급된 기술이 없습니다.</p>;
  return (
    <ChartTips>
      <CloudChart radar={radar} view={view} W={640} H={340} min={12} max={42} className="hidden sm:block" />
      <CloudChart radar={radar} view={view} W={360} H={400} min={11} max={28} className="sm:hidden" />
      <Legend
        className="mt-1"
        items={STATE_ORDER.map((state) => ({ label: STATE_META[state].label, swatch: STATE_FILL[state], shape: "dot" as const }))}
      />
    </ChartTips>
  );
}

function CloudChart({ radar, view, W, H, min, max, className }: { radar: Radar; view: RadarView; W: number; H: number; min: number; max: number; className: string }) {
  const byKey = keywordIndex(radar);
  const words = radar.keywords.map((k) => ({
    key: k.key,
    text: topicLabel("keyword", k),
    weight: k.state === "falling" ? Math.max(last(k.counts), mean(k.counts.slice(0, -1)) * 0.6) : last(k.counts),
  }));
  const placed = wordCloud(words, W, H, min, max);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("h-auto w-full", className)} role="img" aria-label="기술 키워드 워드 클라우드">
        {placed.map((word) => {
          const keyword = byKey.get(word.key)!;
          const state = keyword.state ?? "steady";
          const selected = sameFocus(view.focus, { kind: "keyword", key: word.key });
          return (
            <Link key={word.key} href={keywordHref(radar, view, word.key)} scroll={false} aria-label={`${word.text} ${last(keyword.counts)}건 ${STATE_META[state].label}`}>
              <text
                x={word.x}
                y={word.y}
                fontSize={word.size}
                textAnchor="middle"
                dominantBaseline="central"
                fill={STATE_FILL[state]}
                fontWeight={state === "surging" || state === "new" ? 800 : state === "rising" ? 650 : 500}
                opacity={state === "falling" ? 0.85 : 1}
                textDecoration={selected ? "underline" : undefined}
                data-tip={keywordTip(keyword)}
                className="cursor-pointer transition-opacity hover:opacity-70"
              >
                {word.text}
              </text>
            </Link>
          );
        })}
    </svg>
  );
}

const WATCH: TopicState[] = ["new", "surging", "rising"];

/** The technologies to act on: new, surging and rising keywords ranked by momentum. */
export function EmergingTable({ radar, view, limit = 14 }: { radar: Radar; view: RadarView; limit?: number }) {
  // fresh first (returning, debut), then by lifecycle and momentum
  const rank = (k: Topic) => (k.returning ? 0 : k.debut ? 1 : 2 + WATCH.indexOf(k.state ?? "rising"));
  const rows = radar.keywords
    .filter((k) => k.state !== "falling" && ((k.state && WATCH.includes(k.state)) || k.debut || k.returning))
    .sort((a, b) => rank(a) - rank(b) || b.z - a.z || last(b.counts) - last(a.counts))
    .slice(0, limit);
  if (!rows.length) return <p className="py-10 text-center text-sm text-muted-foreground">새로 뜨거나 늘어난 기술이 없습니다.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">신규·급상승·상승 기술 목록</caption>
        <thead className="text-left text-xs whitespace-nowrap text-muted-foreground">
          <tr className="border-b">
            <th className="py-2 font-medium">기술</th>
            <th className="py-2 font-medium">상태</th>
            <th className="hidden py-2 font-medium sm:table-cell">추이</th>
            <th className="py-2 text-right font-medium">건수</th>
            <th className="py-2 pl-2 text-right font-medium">z</th>
            <th className="hidden py-2 pl-3 text-right font-medium md:table-cell">출처</th>
            <th className="hidden py-2 pl-3 font-medium lg:table-cell">연구 비중</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((keyword) => {
            const share = researchShare(keyword.tracks) ?? 0;
            return (
              <tr key={keyword.key} className={cn("border-b last:border-0", sameFocus(view.focus, { kind: "keyword", key: keyword.key }) && "bg-primary/5")}>
                <td className="max-w-48 py-1.5 pr-2">
                  <Link href={keywordHref(radar, view, keyword.key)} scroll={false} className="block truncate font-medium hover:text-primary">
                    {topicLabel("keyword", keyword)}
                  </Link>
                  {keyword.field ? <span className="block truncate text-[11px] text-muted-foreground">{FIELD_LABEL[keyword.field] ?? keyword.field}</span> : null}
                </td>
                <td className="py-1.5">
                  <span className="flex flex-wrap gap-1">
                    <KeywordBadge topic={keyword} />
                    <StateBadge state={keyword.state} />
                  </span>
                </td>
                <td className="hidden py-1.5 sm:table-cell">
                  <Sparkline values={keyword.counts} width={60} height={20} className={cn(keyword.state === "new" ? "text-primary" : "text-state-hot")} />
                </td>
                <td className="py-1.5 text-right font-semibold tabular-nums">{last(keyword.counts)}</td>
                <td className="py-1.5 pl-2 text-right whitespace-nowrap text-ink-2 tabular-nums">{formatZ(keyword.z)}</td>
                <td className="hidden py-1.5 pl-3 text-right text-ink-2 tabular-nums md:table-cell">{keyword.sources}</td>
                <td className="hidden py-1.5 pl-3 lg:table-cell">
                  <span className="flex items-center gap-1.5" title={`논문·오픈소스 ${Math.round(share * 100)}%`}>
                    <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-muted" aria-hidden>
                      <span className="absolute inset-y-0 left-0 rounded-full bg-viz-research" style={{ width: `${Math.round(share * 100)}%` }} />
                    </span>
                    <span className="w-9 text-right text-xs whitespace-nowrap text-muted-foreground tabular-nums">{Math.round(share * 100)}%</span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Keywords named together; thicker = more joint mentions, new links in the accent colour. */
export function ConvergenceNetwork({ radar, view }: { radar: Radar; view: RadarView }) {
  if (!radar.pairs.length) return <p className="py-16 text-center text-sm text-muted-foreground">함께 2번 이상 언급된 기술 쌍이 없습니다.</p>;
  return (
    <ChartTips>
      <NetworkChart radar={radar} view={view} W={640} H={380} limit={22} className="hidden sm:block" />
      <NetworkChart radar={radar} view={view} W={380} H={420} limit={14} className="sm:hidden" />
      <Legend
        className="mt-1"
        items={[
          ...STATE_ORDER.map((state) => ({ label: `기술: ${STATE_META[state].label}`, swatch: STATE_FILL[state], shape: "dot" as const })),
          { label: "선: 첫 동시 언급", swatch: "var(--primary)" },
          { label: "선: 이전부터", swatch: "var(--muted-foreground)" },
        ]}
      />
    </ChartTips>
  );
}

function NetworkChart({ radar, view, W, H, limit, className }: { radar: Radar; view: RadarView; W: number; H: number; limit: number; className: string }) {
  const pairs = radar.pairs.slice(0, limit);
  const byKey = keywordIndex(radar);
  const nodes = [...new Set(pairs.flatMap((p) => [p.a, p.b]))];
  const pos = forceLayout(nodes, pairs.map((p) => ({ a: p.a, b: p.b, weight: p.count })), W, H, 48);
  const maxCount = Math.max(...pairs.map((p) => p.count));
  const size = (key: string) => 5 + Math.sqrt(last(byKey.get(key)?.counts ?? [1])) * 1.8;
  const focusKey = view.focus?.kind === "keyword" ? view.focus.key : null;
  const label = (key: string) => (byKey.get(key) ? topicLabel("keyword", byKey.get(key)!) : key);
  const cross = (a: string, b: string) => {
    const fa = byKey.get(a)?.field, fb = byKey.get(b)?.field;
    return !!fa && !!fb && fa !== fb;
  };
  // labels: above, below, right, left of the node; dropped (tooltip only) when all four collide
  const boxes = nodes.map((key) => ({ ...pos.get(key)!, r: size(key) }));
  const labels: { key: string; x: number; y: number; w: number }[] = [];
  const free = (x: number, y: number, w: number) =>
    x - w / 2 >= 0 && x + w / 2 <= W && y - 11 >= 0 && y + 3 <= H &&
    !labels.some((o) => Math.abs(o.x - x) * 2 < o.w + w && Math.abs(o.y - y) < 14) &&
    !boxes.some((b) => b.x + b.r > x - w / 2 && b.x - b.r < x + w / 2 && b.y + b.r > y - 11 && b.y - b.r < y + 3);
  for (const key of [...nodes].sort((a, b) => size(b) - size(a))) {
    const p = pos.get(key)!, r = size(key), w = textWidth(label(key), 11.5);
    const spot = [
      [p.x, p.y - r - 5],
      [p.x, p.y + r + 13],
      [p.x + r + 4 + w / 2, p.y + 4],
      [p.x - r - 4 - w / 2, p.y + 4],
    ].find(([x, y]) => free(x, y, w));
    if (spot) labels.push({ key, x: spot[0], y: spot[1], w });
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("h-auto w-full", className)} role="img" aria-label="기술 동시 언급 네트워크">
        {pairs.map((pair) => {
          const a = pos.get(pair.a)!, b = pos.get(pair.b)!;
          const lit = focusKey === pair.a || focusKey === pair.b;
          return (
            <g key={`${pair.a}-${pair.b}`} data-tip={`${label(pair.a)} × ${label(pair.b)}\n함께 ${pair.count}건\n우연 대비 ${pair.lift.toFixed(1)}배${pair.is_new ? " · 첫 동시 언급" : ""}${cross(pair.a, pair.b) ? " · 다른 카테고리" : ""}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={12} />
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={pair.is_new ? "var(--primary)" : "var(--muted-foreground)"}
                strokeOpacity={focusKey && !lit ? 0.15 : pair.is_new ? 0.9 : 0.5}
                strokeWidth={1 + (pair.count / maxCount) * 4}
                strokeLinecap="round"
              />
            </g>
          );
        })}
        {nodes.map((key) => {
          const p = pos.get(key)!;
          const keyword = byKey.get(key);
          const r = size(key);
          const dim = focusKey && focusKey !== key && !pairs.some((x) => (x.a === focusKey && x.b === key) || (x.b === focusKey && x.a === key));
          return (
            <Link key={key} href={keywordHref(radar, view, key)} scroll={false} aria-label={label(key)}>
              <g data-tip={keyword ? keywordTip(keyword) : label(key)} opacity={dim ? 0.35 : 1} className="cursor-pointer">
                <circle cx={p.x} cy={p.y} r={Math.max(r + 4, 12)} fill="transparent" />
                <circle cx={p.x} cy={p.y} r={r} fill={STATE_FILL[keyword?.state ?? "steady"]} stroke={focusKey === key ? "var(--foreground)" : "var(--card)"} strokeWidth={2} />
              </g>
            </Link>
          );
        })}
        {labels.map((item) => (
          <text key={item.key} x={item.x} y={item.y} fontSize={11.5} fontWeight={600} textAnchor="middle" fill="var(--foreground)" paintOrder="stroke" stroke="var(--card)" strokeWidth={3} className="pointer-events-none">
            {label(item.key)}
          </text>
        ))}
    </svg>
  );
}

export function PairList({ radar, view, limit = 8 }: { radar: Radar; view: RadarView; limit?: number }) {
  const byKey = keywordIndex(radar);
  const label = (key: string) => (byKey.get(key) ? topicLabel("keyword", byKey.get(key)!) : key);
  const rows = [...radar.pairs].sort((a, b) => b.lift * Math.log(b.count + 1) - a.lift * Math.log(a.count + 1)).slice(0, limit);
  if (!rows.length) return null;
  const focus = (key: string): Focus => ({ kind: "keyword", key });
  return (
    <ol className="space-y-1.5 text-sm">
      {rows.map((pair) => (
        <li key={`${pair.a}-${pair.b}`} className="flex items-center gap-2 rounded-lg bg-muted/60 px-2.5 py-1.5">
          <span className="min-w-0 flex-1 truncate">
            <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus: focus(pair.a) })} scroll={false} className="font-medium hover:text-primary">
              {label(pair.a)}
            </Link>
            <span className="mx-1 text-muted-foreground">×</span>
            <Link href={radarHref(radar.window.kind, radar.window.key, { ...view, focus: focus(pair.b) })} scroll={false} className="font-medium hover:text-primary">
              {label(pair.b)}
            </Link>
          </span>
          {pair.is_new ? <span className="rounded-full bg-primary/12 px-1.5 text-[11px] font-semibold text-primary">신규</span> : null}
          <span className="text-xs text-muted-foreground tabular-nums">{pair.count}건 · {pair.lift.toFixed(1)}배</span>
        </li>
      ))}
    </ol>
  );
}
