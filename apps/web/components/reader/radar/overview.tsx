import { ArrowRightLeft, FlaskConical, Flame, Globe2, Link2, SearchCheck, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import Link from "next/link";

import { Change } from "@/components/reader/radar/parts";
import { Sparkline } from "@/components/reader/sparkline";
import { formatNumber } from "@/lib/format";
import { changePercent, formatPoints, last, projected, radarHref, type RadarView } from "@/lib/radar";
import { radarSignals, SIGNAL_META, type SignalTone } from "@/lib/radar-signals";
import type { Radar } from "@/lib/reader-types";
import { cn } from "@/lib/utils";

function Tile({ label, value, note, trend }: { label: string; value: string; note: React.ReactNode; trend?: number[] }) {
  return (
    <div className="flex min-w-0 flex-col justify-between gap-2 rounded-2xl border bg-card px-4 py-3 shadow-xs">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <div className="flex items-end justify-between gap-2">
        <dd className="text-2xl leading-none font-bold tracking-tight">{value}</dd>
        {trend && trend.length > 1 ? (
          <Sparkline values={trend} width={72} height={24} className="text-primary" label={`${label} 추이 ${trend.join(", ")}`} />
        ) : null}
      </div>
      <dd className="text-xs text-muted-foreground">{note}</dd>
    </div>
  );
}

export function KpiStrip({ radar }: { radar: Radar }) {
  const { kpis } = radar;
  const share = kpis.items.map((items, i) => (items ? (kpis.research[i] / items) * 100 : 0));
  const prevShare = share[share.length - 2] ?? 0;
  const newTech = radar.keywords.filter((k) => k.state === "new").length;
  const surgingTech = radar.keywords.filter((k) => k.state === "surging").length;
  const activeThemes = radar.themes.filter((t) => last(t.counts) > 0);
  const risingThemes = activeThemes.filter((t) => t.z >= 1).length;
  const pace = projected(last(kpis.items), radar.window.elapsed);
  const vs = (values: number[]) => <><Change value={changePercent(last(values), values[values.length - 2] ?? 0)} /> 직전 기간 대비</>;
  return (
    <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Tile
        label="분석 기사"
        value={formatNumber(last(kpis.items))}
        note={pace ? <>{vs(kpis.items)} · 지금 속도면 약 {formatNumber(pace)}건</> : vs(kpis.items)}
        trend={kpis.items}
      />
      <Tile label="이슈 (중복 보도 묶음)" value={formatNumber(last(kpis.stories))} note={<>새 이슈 {kpis.new_stories} · 여러 트랙 {kpis.cross_track_stories}</>} trend={kpis.stories} />
      <Tile label="참여 출처" value={formatNumber(last(kpis.sources))} note={vs(kpis.sources)} trend={kpis.sources} />
      <Tile
        label="연구·오픈소스 비중"
        value={`${last(share).toFixed(0)}%`}
        note={<>{formatPoints(last(share) - prevShare)} · 높을수록 초기 신호 많음</>}
        trend={share.map((v) => Math.round(v))}
      />
      <Tile label="신규·급상승 기술" value={`${newTech} · ${surgingTech}`} note="키워드 기준, 출처 2곳 이상" />
      <Tile label="상승세 테마" value={`${risingThemes}/${activeThemes.length}`} note="z ≥ +1σ인 테마 / 언급된 테마" />
    </dl>
  );
}

const SIGNAL_ICON: Record<SignalTone, typeof Flame> = {
  surge: Flame,
  new: Sparkles,
  early: FlaskConical,
  shift: ArrowRightLeft,
  hype: TrendingUp,
  thin: SearchCheck,
  gap: Globe2,
  link: Link2,
  cool: TrendingDown,
};
const SIGNAL_TONE: Record<SignalTone, string> = {
  surge: "text-state-hot bg-state-hot/12",
  new: "text-primary bg-primary/12",
  early: "text-track-research bg-track-research/12",
  shift: "text-track-oss bg-track-oss/12",
  hype: "text-track-community bg-track-community/12",
  thin: "text-impact-risk bg-impact-risk/12",
  gap: "text-track-news bg-track-news/12",
  link: "text-track-news bg-track-news/12",
  cool: "text-state-cool bg-state-cool/12",
};

/** What changed and when to look: rule-based readings of the stats below. */
export function SignalCards({ radar, view }: { radar: Radar; view: RadarView }) {
  const signals = radarSignals(radar);
  if (!signals.length) {
    return <p className="rounded-2xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">이번 기간에는 기준을 넘는 뚜렷한 신호가 없습니다. 기간을 넓히거나 범위를 &lsquo;전체&rsquo;로 바꿔 보세요.</p>;
  }
  return (
    <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="핵심 신호">
      {signals.map((signal) => {
        const Icon = SIGNAL_ICON[signal.tone];
        return (
          <li key={signal.tone}>
            <Link
              href={radarHref(radar.window.kind, radar.window.key, { ...view, focus: signal.focus })}
              scroll={false}
              className="group flex h-full gap-3 rounded-2xl border bg-card p-3.5 shadow-xs transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl", SIGNAL_TONE[signal.tone])}>
                <Icon className="size-4.5" aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block text-[11px] font-semibold text-muted-foreground">{SIGNAL_META[signal.tone].label}</span>
                <span className="block font-bold leading-snug group-hover:text-primary">{signal.title}</span>
                <span className="mt-0.5 block text-xs leading-relaxed text-ink-2">{signal.detail}</span>
              </span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
