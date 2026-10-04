/// <reference types="react/canary" />
import Link from "next/link";
import { ViewTransition } from "react";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { Change, Legend, StateBadge } from "@/components/reader/radar/parts";
import { formatDateTime, formatRelative, REGION_LABEL, TRACK_LABEL } from "@/lib/format";
import {
  BASELINE_UNIT,
  businessShort,
  focusParam,
  formatZ,
  last,
  mean,
  periodLabel,
  projected,
  radarHref,
  REGIONS,
  type RadarView,
  researchShare,
  STAGE_META,
  stageOf,
  sumMix,
  topicLabel,
} from "@/lib/radar";
import { withQuery } from "@/lib/query";
import type { Radar, TopicDetail, TrackMix } from "@/lib/reader-types";
import type { Region, Track } from "@/lib/types";
import { BUSINESS_LABEL, FIELD_LABEL, IMPACT_LABEL, THEME_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const KIND_LABEL = { field: "카테고리", theme: "테마", keyword: "기술" } as const;
const TRACK_ORDER: Track[] = ["research_ip", "oss", "community", "news"];
const TRACK_FILL: Record<Track, string> = {
  research_ip: "var(--viz-research)",
  oss: "var(--viz-oss)",
  community: "var(--viz-community)",
  news: "var(--viz-news)",
};

function Trend({ counts, periods, forecast }: { counts: number[]; periods: string[]; forecast: number | null }) {
  const W = 320, H = 120, B = 18, T = 14;
  const max = Math.max(...counts, forecast ?? 0, 1);
  const base = mean(counts.slice(0, -1));
  const slot = W / counts.length;
  const bar = Math.min(24, slot * 0.6);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`기간별 건수 ${counts.join(", ")}`}>
      <line x1={0} x2={W} y1={H - B} y2={H - B} stroke="var(--border)" />
      {counts.map((count, i) => {
        const x = i * slot + (slot - bar) / 2;
        const h = H - B - y(count);
        const current = i === counts.length - 1;
        return (
          <g key={periods[i]} data-tip={`${periods[i]}\n${count}건${current && forecast !== null ? `\n지금 속도면 약 ${forecast}건` : ""}`}>
            <rect x={i * slot} y={0} width={slot} height={H} fill="transparent" />
            {current && forecast !== null && forecast > count ? (
              <rect x={x} y={y(forecast)} width={bar} height={H - B - y(forecast)} rx={4} fill="var(--primary)" fillOpacity={0.14} />
            ) : null}
            {count ? (
              <path
                d={`M${x},${H - B} v${-Math.max(h - 4, 0)} q0,-4 4,-4 h${bar - 8} q4,0 4,4 v${Math.max(h - 4, 0)} z`}
                fill={current ? "var(--primary)" : "var(--muted-foreground)"}
                fillOpacity={current ? 1 : 0.35}
              />
            ) : null}
            {current || count === max ? (
              <text x={x + bar / 2} y={y(current && forecast !== null ? Math.max(count, forecast) : count) - 4} fontSize={11} fontWeight={700} textAnchor="middle" fill="var(--foreground)">
                {count}
              </text>
            ) : null}
            <text x={x + bar / 2} y={H - 4} fontSize={10} textAnchor="middle" fill={current ? "var(--foreground)" : "var(--muted-foreground)"}>
              {periodLabel(periods[i])}
            </text>
          </g>
        );
      })}
      <line x1={0} x2={W} y1={y(base)} y2={y(base)} stroke="var(--state-hot)" strokeWidth={1.5} strokeOpacity={0.8} />
      <text x={2} y={y(base) - 4} fontSize={10} fill="var(--ink-2)" paintOrder="stroke" stroke="var(--card)" strokeWidth={3}>
        직전 평균 {base.toFixed(1)}
      </text>
    </svg>
  );
}

function Mix({ label, mix }: { label: string; mix: TrackMix }) {
  const total = sumMix(mix);
  return (
    <div className="grid grid-cols-[3rem_minmax(0,1fr)_2.5rem] items-center gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex h-3 gap-0.5 overflow-hidden rounded-[3px] bg-muted">
        {total
          ? TRACK_ORDER.map((track) =>
              mix[track] ? <span key={track} data-tip={`${label} · ${TRACK_LABEL[track]}\n${mix[track]}건`} style={{ flex: mix[track], background: TRACK_FILL[track] }} /> : null,
            )
          : null}
      </span>
      <span className="text-right tabular-nums text-muted-foreground">{total}</span>
    </div>
  );
}

function Bars({ rows, label, total }: { rows: { key: string; count: number }[]; label: (key: string) => string; total: number }) {
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <ul className="space-y-1">
      {rows.map((row) => (
        <li key={row.key} className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)_3.5rem] items-center gap-2 text-xs">
          <span className="truncate" title={label(row.key)}>{label(row.key)}</span>
          <span className="h-2 overflow-hidden rounded-r-[4px] bg-muted">
            <span className="block h-full rounded-r-[4px] bg-primary/70" style={{ width: `${(row.count / max) * 100}%` }} />
          </span>
          <span className="text-right text-muted-foreground tabular-nums">
            {row.count}
            {total ? ` · ${Math.round((row.count / total) * 100)}%` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t pt-3">
      <h3 className="mb-2 text-xs font-semibold text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

export function TopicPanel({ detail, radar, view }: { detail: TopicDetail; radar: Radar; view: RadarView }) {
  const { topic, kind } = detail;
  const current = last(topic.counts);
  const share = researchShare(topic.tracks);
  const before = researchShare(topic.previous_tracks);
  const stage = stageOf(share);
  const firstSeen = (Object.entries(topic.first_seen) as [Region, string][]).sort((a, b) => Date.parse(a[1]) - Date.parse(b[1]));
  const impactTotal = topic.impacts.opportunity + topic.impacts.risk + topic.impacts.watch;
  const at = (focus: { kind: "field" | "theme" | "keyword"; key: string }) => radarHref(radar.window.kind, radar.window.key, { ...view, focus });
  const field = kind === "field" ? topic.key : kind === "theme" ? topic.key.split("__")[0] : topic.field;
  const period = radar.window.kind === "day" ? "1d" : radar.window.kind === "week" ? "7d" : "30d";
  const explore = withQuery("/", {
    field: kind === "field" ? topic.key : undefined,
    theme: kind === "theme" ? topic.key : undefined,
    q: kind === "keyword" ? topicLabel(kind, topic) : undefined,
    business: view.business,
    scope: view.scope !== "relevant" ? view.scope : undefined,
    period,
  });

  return (
    <ViewTransition key={`${focusParam({ kind, key: topic.key })}`} name="radar-topic" share="auto" enter="auto" default="none">
      <ChartTips className="space-y-4">
        <header>
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span className="rounded bg-muted px-1.5 py-px font-semibold text-ink-2">{KIND_LABEL[kind]}</span>
            {kind !== "field" && field && field in FIELD_LABEL ? (
              <Link href={at({ kind: "field", key: field })} scroll={false} className="hover:text-primary">
                {FIELD_LABEL[field]}
              </Link>
            ) : null}
          </p>
          <h2 className="mt-1 flex flex-wrap items-center gap-2 text-xl leading-snug font-bold tracking-tight">
            {topicLabel(kind, topic)}
            <StateBadge state={topic.state} />
          </h2>
          <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
            {[
              ["언급", `${current}건`],
              ["직전 대비", <Change key="c" value={topic.change} />],
              ["모멘텀", formatZ(topic.z)],
              ["출처", `${topic.sources}곳`],
              ["실효 출처", topic.effective_sources !== null ? `${topic.effective_sources.toFixed(1)}곳` : "–"],
              ["공식 발표", current ? `${Math.round((topic.official / current) * 100)}%` : "–"],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl bg-muted/70 px-1 py-2">
                <dt className="text-[11px] text-muted-foreground">{label}</dt>
                <dd className="text-sm font-bold">{value}</dd>
              </div>
            ))}
          </dl>
        </header>

        <Section title={`최근 ${topic.counts.length}개 기간 (선 = 직전 ${topic.counts.length - 1}${BASELINE_UNIT[radar.window.kind]} 평균)`}>
          <Trend counts={topic.counts} periods={radar.periods} forecast={projected(current, radar.window.elapsed)} />
        </Section>

        <Section title="신호 단계 · 트랙 구성">
          <div className="space-y-1.5">
            <Mix label="이번" mix={topic.tracks} />
            <Mix label="직전" mix={topic.previous_tracks} />
          </div>
          <p className="mt-2 text-xs text-ink-2">
            {stage ? <b className="text-foreground">{STAGE_META[stage].label}</b> : null}
            {share !== null ? ` · 논문·오픈소스 ${Math.round(share * 100)}%` : ""}
            {share !== null && before !== null ? ` (직전 ${Math.round(before * 100)}%)` : ""}
            {stage ? ` · ${STAGE_META[stage].hint}` : ""}
          </p>
          <Legend className="mt-2" items={TRACK_ORDER.map((track) => ({ label: TRACK_LABEL[track], swatch: TRACK_FILL[track] }))} />
        </Section>

        {impactTotal ? (
          <Section title="영향 분류">
            <div className="flex h-3 gap-0.5 overflow-hidden rounded-[3px]">
              {(["opportunity", "risk", "watch"] as const).map((impact) =>
                topic.impacts[impact] ? (
                  <span key={impact} data-tip={`${IMPACT_LABEL[impact]}\n${topic.impacts[impact]}건`} style={{ flex: topic.impacts[impact], background: `var(--impact-${impact})` }} />
                ) : null,
              )}
            </div>
            <p className="mt-1.5 flex gap-3 text-xs text-muted-foreground">
              {(["opportunity", "risk", "watch"] as const).map((impact) => (
                <span key={impact}>
                  {IMPACT_LABEL[impact]} <b className="text-foreground tabular-nums">{Math.round((topic.impacts[impact] / impactTotal) * 100)}%</b>
                </span>
              ))}
            </p>
          </Section>
        ) : null}

        {detail.themes.length ? (
          <Section title={kind === "field" ? "테마" : "걸쳐 있는 테마"}>
            <Bars rows={detail.themes.slice(0, 6)} label={(key) => THEME_LABEL[key] ?? key} total={current} />
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {detail.themes.slice(0, 6).map((theme) => (
                <Link key={theme.key} href={at({ kind: "theme", key: theme.key })} scroll={false} className="text-xs text-primary hover:underline">
                  {THEME_LABEL[theme.key] ?? theme.key} →
                </Link>
              ))}
            </div>
          </Section>
        ) : null}

        {detail.keywords.length ? (
          <Section title={kind === "keyword" ? "함께 언급된 기술" : "많이 언급된 기술"}>
            <div className="flex flex-wrap gap-1.5">
              {detail.keywords.map((keyword) => (
                <Link
                  key={keyword.key}
                  href={at({ kind: "keyword", key: keyword.key })}
                  scroll={false}
                  className="rounded-full border bg-background px-2.5 py-0.5 text-xs text-ink-2 transition hover:border-primary hover:text-primary"
                >
                  {keyword.label} <span className="text-muted-foreground tabular-nums">{keyword.count}</span>
                </Link>
              ))}
            </div>
          </Section>
        ) : null}

        {detail.businesses.length ? (
          <Section title="연관 DX 사업부">
            <Bars rows={detail.businesses} label={(key) => `${businessShort(key)} · ${(BUSINESS_LABEL[key] ?? key).split(" · ")[1] ?? ""}`} total={current} />
          </Section>
        ) : null}

        {current ? (
          <Section title="지역 · 처음 보도된 순서">
            <Bars
              rows={REGIONS.filter((r) => topic.regions[r]).map((r) => ({ key: r, count: topic.regions[r] }))}
              label={(key) => REGION_LABEL[key as Region] ?? key}
              total={current}
            />
            {firstSeen.length > 1 ? (
              <ol className="mt-2 flex flex-wrap items-center gap-x-1 gap-y-1 text-xs text-ink-2">
                {firstSeen.map(([region, at], i) => (
                  <li key={region} className="flex items-center gap-1">
                    {i ? <span className="text-muted-foreground">→</span> : null}
                    <span className={cn("rounded-full px-1.5 py-px", region === "kr" ? "bg-primary/12 font-semibold text-primary" : "bg-muted")}>
                      {REGION_LABEL[region]} {i ? `+${((Date.parse(at) - Date.parse(firstSeen[0][1])) / 86_400_000).toFixed(1)}일` : formatDateTime(at).split(" ")[0]}
                    </span>
                  </li>
                ))}
              </ol>
            ) : null}
          </Section>
        ) : null}

        <Section title="대표 이슈">
          {detail.stories.length ? (
            <ul className="space-y-1.5">
              {detail.stories.map((story) => (
                <li key={story.id}>
                  <Link href={`/items/${story.id}`} className="block rounded-xl border px-3 py-2 text-sm leading-snug transition hover:border-primary/50 hover:bg-muted/40">
                    {story.title_ko ?? story.title}
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {TRACK_LABEL[story.track]} · {story.source_name} · {formatRelative(story.first_seen_at)}
                      {story.story && story.story.item_count > 1 ? ` · 보도 ${story.story.item_count}건` : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">이 기간에 해당하는 기사가 없습니다.</p>
          )}
        </Section>

        <Link href={explore} className={cn("inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline")}>
          탐색에서 기사 모두 보기 →
        </Link>
      </ChartTips>
    </ViewTransition>
  );
}
