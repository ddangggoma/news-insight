import Link from "next/link";

import { Sparkline } from "@/components/reader/sparkline";
import { formatNumber, formatRelative } from "@/lib/format";
import {
  BUSINESS_COLUMNS,
  businessLabel,
  type CellRef,
  cellIndex,
  changePercent,
  formatChange,
  heatLevel,
  RADAR_KINDS,
  shortBusiness,
} from "@/lib/radar";
import { withQuery } from "@/lib/query";
import type { CellDetail, Radar, RadarKind } from "@/lib/reader-types";
import { SCOPES, type Scope } from "@/lib/reader-filters";
import { FIELD_LABEL, THEME_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

export type RadarView = { scope: Scope; cell: CellRef | null; table: boolean; allRows: boolean };

export function radarHref(kind: string, key: string, view: Partial<RadarView>): string {
  return withQuery(`/radar/${kind}/${key}`, {
    scope: view.scope && view.scope !== "relevant" ? view.scope : undefined,
    cell: view.cell ? `${view.cell.field}.${view.cell.business}` : undefined,
    view: view.table ? "table" : undefined,
    rows: view.allRows ? "all" : undefined,
  });
}

function Change({ value }: { value: number | null }) {
  return (
    <span className={cn("tabular-nums", value === null ? "text-muted-foreground" : value >= 0 ? "text-impact-opportunity" : "text-impact-risk")}>
      {formatChange(value)}
    </span>
  );
}

export function RadarControls({ radar, view }: { radar: Radar; view: RadarView }) {
  const { window } = radar;
  const keep = { scope: view.scope, table: view.table, allRows: view.allRows };
  return (
    <div className="flex flex-wrap items-center gap-3 border-b pb-4">
      <nav aria-label="기간 단위" className="inline-flex rounded-lg bg-muted p-0.5">
        {(Object.keys(RADAR_KINDS) as RadarKind[]).map((kind) => (
          <Link
            key={kind}
            href={withQuery("/radar", { period: kind, scope: view.scope !== "relevant" ? view.scope : undefined })}
            aria-current={window.kind === kind ? "true" : undefined}
            className={cn(
              "rounded-md px-3 py-1 text-sm text-muted-foreground",
              window.kind === kind && "bg-background font-semibold text-foreground shadow-sm",
            )}
          >
            {RADAR_KINDS[kind]}
          </Link>
        ))}
      </nav>
      <div className="flex items-center gap-1 text-sm">
        <Link href={radarHref(window.kind, window.prev_key, keep)} aria-label="이전 기간" className="rounded px-2 py-1 hover:bg-muted">
          ‹
        </Link>
        <span className="font-semibold tabular-nums">{window.key}</span>
        {window.is_current ? (
          <span className="rounded px-2 py-1 text-muted-foreground" aria-hidden>
            ›
          </span>
        ) : (
          <Link href={radarHref(window.kind, window.next_key, keep)} aria-label="다음 기간" className="rounded px-2 py-1 hover:bg-muted">
            ›
          </Link>
        )}
        {window.is_current ? <span className="ml-1 rounded bg-primary/10 px-1.5 text-xs text-primary">진행 중</span> : null}
      </div>
      <nav aria-label="범위" className="ml-auto flex flex-wrap gap-1 text-sm">
        {(Object.keys(SCOPES) as Scope[]).map((scope) => (
          <Link
            key={scope}
            href={radarHref(window.kind, window.key, { ...keep, scope })}
            aria-current={view.scope === scope ? "true" : undefined}
            className={cn("rounded-md px-2.5 py-1 text-muted-foreground hover:bg-muted", view.scope === scope && "bg-primary/10 font-semibold text-primary")}
          >
            {SCOPES[scope]}
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function KpiStrip({ radar }: { radar: Radar }) {
  const { kpis } = radar;
  const hottest = kpis.hottest;
  const tiles = [
    { label: "분석 기사", value: formatNumber(kpis.total), note: <><Change value={changePercent(kpis.total, kpis.previous_total)} /> 직전 기간 대비</> },
    { label: "새 이슈", value: formatNumber(kpis.new_stories), note: "이번 기간에 처음 묶인 사건" },
    {
      label: "가장 빠르게 뜨는 칸",
      value: hottest ? `${FIELD_LABEL[hottest.field]} × ${shortBusiness(hottest.business)}` : "—",
      note: hottest ? <><Change value={changePercent(hottest.count, hottest.previous)} /> {hottest.count}건</> : "2건 이상인 칸이 없습니다",
      small: true,
    },
    { label: "여러 트랙에 걸친 이슈", value: formatNumber(kpis.cross_track_stories), note: "논문·오픈소스·커뮤니티·뉴스 중 2개 이상" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.label} className="rounded-xl border bg-card px-4 py-3">
          <dt className="text-xs text-muted-foreground">{tile.label}</dt>
          <dd className={cn("mt-0.5 font-semibold tabular-nums", tile.small ? "text-base leading-snug" : "text-2xl")}>{tile.value}</dd>
          <dd className="mt-0.5 text-xs text-muted-foreground">{tile.note}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Heatmap({ radar, rows, view }: { radar: Radar; rows: string[]; view: RadarView }) {
  const index = cellIndex(radar.cells);
  const max = Math.max(0, ...radar.cells.map((cell) => cell.count));
  const { kind, key } = radar.window;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-separate border-spacing-[3px] text-xs">
        <caption className="sr-only">기술 분야별·DX 사업부별 기사 수와 직전 기간 대비 변화</caption>
        <thead>
          <tr>
            <th scope="col" className="sticky left-0 bg-card" />
            {BUSINESS_COLUMNS.map((business) => (
              <th key={business} scope="col" title={businessLabel(business)} className="px-1 pb-1 font-medium whitespace-nowrap text-muted-foreground">
                {shortBusiness(business)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((field) => (
            <tr key={field}>
              <th scope="row" className="sticky left-0 z-10 bg-card pr-2 text-right font-medium whitespace-nowrap text-ink-2">
                {FIELD_LABEL[field]}
              </th>
              {BUSINESS_COLUMNS.map((business) => {
                const cell = index.get(`${field}.${business}`);
                const count = cell?.count ?? 0;
                const change = changePercent(count, cell?.previous ?? 0);
                const level = heatLevel(count, max);
                const selected = view.cell?.field === field && view.cell.business === business;
                const label = `${FIELD_LABEL[field]} × ${businessLabel(business)}: ${count}건, 직전 ${cell?.previous ?? 0}건`;
                return (
                  <td key={business} className="p-0">
                    <Link
                      href={radarHref(kind, key, { ...view, cell: { field, business } })}
                      scroll={false}
                      aria-label={label}
                      title={label}
                      aria-current={selected ? "true" : undefined}
                      className={cn(
                        "grid h-10 min-w-12 place-items-center rounded-md leading-tight tabular-nums",
                        level >= 50 ? "font-semibold text-heat-ink" : "text-ink-2",
                        selected && "outline-2 outline-offset-1 outline-foreground",
                      )}
                      style={{ background: `color-mix(in oklab, var(--heat) ${level}%, var(--muted))` }}
                    >
                      <span>{count ? formatNumber(count) : "·"}</span>
                      {count || cell?.previous ? <span className="text-[10px]">{formatChange(change)}</span> : null}
                    </Link>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HeatmapTable({ radar }: { radar: Radar }) {
  const rows = [...radar.cells].filter((cell) => cell.count || cell.previous).sort((a, b) => b.count - a.count);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">분야 × 사업부 표</caption>
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th className="py-2 font-medium">기술 분야</th>
            <th className="py-2 font-medium">DX 사업부</th>
            <th className="py-2 text-right font-medium">기사</th>
            <th className="py-2 text-right font-medium">직전</th>
            <th className="py-2 text-right font-medium">변화</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((cell) => (
            <tr key={`${cell.field}.${cell.business}`} className="border-b last:border-0">
              <td className="py-1.5">{FIELD_LABEL[cell.field]}</td>
              <td className="py-1.5">{businessLabel(cell.business)}</td>
              <td className="py-1.5 text-right tabular-nums">{formatNumber(cell.count)}</td>
              <td className="py-1.5 text-right text-muted-foreground tabular-nums">{formatNumber(cell.previous)}</td>
              <td className="py-1.5 text-right">
                <Change value={changePercent(cell.count, cell.previous)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CellPanel({ detail, radar, scope }: { detail: CellDetail; radar: Radar; scope: Scope }) {
  return (
    <div className="space-y-5">
      <header>
        <p className="text-xs text-muted-foreground">선택한 칸</p>
        <h2 className="text-lg leading-snug font-bold">
          {FIELD_LABEL[detail.field]} × {businessLabel(detail.business)}
        </h2>
        <p className="text-sm text-muted-foreground">
          <b className="text-foreground tabular-nums">{formatNumber(detail.count)}건</b> · <Change value={changePercent(detail.count, detail.previous)} /> 직전 기간 대비
        </p>
      </header>
      <section>
        <h3 className="mb-1 text-xs font-semibold text-muted-foreground">최근 8개 기간</h3>
        <Sparkline values={detail.trend} width={280} height={52} className="w-full text-heat" label={`최근 8개 기간 기사 수 ${detail.trend.join(", ")}`} />
      </section>
      {detail.themes.length ? (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">테마</h3>
          <ul className="space-y-1 text-sm">
            {detail.themes.map((theme) => (
              <li key={theme.key} className="flex justify-between gap-2">
                <span>{THEME_LABEL[theme.key] ?? theme.key}</span>
                <span className="text-muted-foreground tabular-nums">{theme.count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {detail.keywords.length ? (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">많이 언급된 키워드</h3>
          <div className="flex flex-wrap gap-1.5">
            {detail.keywords.map((keyword) => (
              <span key={keyword.key} className="rounded-md bg-muted px-2 py-0.5 text-xs text-ink-2">
                {keyword.label} <span className="tabular-nums text-muted-foreground">{keyword.count}</span>
              </span>
            ))}
          </div>
        </section>
      ) : null}
      <section>
        <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">대표 이슈</h3>
        {detail.stories.length ? (
          <ul className="space-y-1.5">
            {detail.stories.map((story) => (
              <li key={story.id}>
                <Link href={`/items/${story.id}`} className="block rounded-lg border px-3 py-2 text-sm leading-snug hover:border-heat">
                  {story.title_ko ?? story.title}
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {story.source_name} · {formatRelative(story.first_seen_at)}
                    {story.story && story.story.item_count > 1 ? ` · 보도 ${story.story.item_count}건` : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">이 기간에 해당하는 기사가 없습니다.</p>
        )}
      </section>
      <Link
        href={withQuery("/", {
          field: detail.field,
          business: detail.business === "none" ? undefined : detail.business,
          scope: scope !== "relevant" ? scope : undefined,
          period: radar.window.kind === "day" ? "1d" : radar.window.kind === "week" ? "7d" : "30d",
        })}
        className="inline-block text-sm font-medium text-primary hover:underline"
      >
        이 조합으로 탐색 →
      </Link>
    </div>
  );
}

export function MomentumTable({ radar }: { radar: Radar }) {
  const rows = radar.momentum.slice(0, 12);
  const total = rows.reduce((sum, row) => sum + row.counts[row.counts.length - 1], 0);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th className="py-2 font-medium">기술 분야</th>
            <th className="py-2 text-right font-medium">기사</th>
            <th className="py-2 text-right font-medium">변화</th>
            <th className="hidden py-2 pl-4 font-medium sm:table-cell">최근 8개 기간</th>
            <th className="hidden py-2 text-right font-medium sm:table-cell">점유율</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const current = row.counts[row.counts.length - 1];
            return (
              <tr key={row.key} className="border-b last:border-0">
                <td className="py-1.5">{FIELD_LABEL[row.key] ?? row.key}</td>
                <td className="py-1.5 text-right tabular-nums">{formatNumber(current)}</td>
                <td className="py-1.5 text-right">
                  <Change value={row.change} />
                </td>
                <td className="hidden py-1.5 pl-4 sm:table-cell">
                  <Sparkline values={row.counts} width={88} height={20} className={row.change !== null && row.change < 0 ? "text-impact-risk" : "text-impact-opportunity"} />
                </td>
                <td className="hidden py-1.5 text-right text-muted-foreground tabular-nums sm:table-cell">
                  {total ? `${((current / total) * 100).toFixed(1)}%` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Fields placed by how fast news/community volume grew (x) against papers/open source (y). */
export function HypeScatter({ radar }: { radar: Radar }) {
  const points = radar.hype.filter(
    (point): point is typeof point & { chatter_change: number; research_change: number } =>
      point.chatter_change !== null && point.research_change !== null,
  );
  const missing = radar.hype.length - points.length;
  if (!points.length) {
    return <p className="py-8 text-center text-sm text-muted-foreground">직전 기간과 비교할 수 있는 분야가 아직 없습니다.</p>;
  }
  const W = 520, H = 300, L = 46, R = 16, T = 14, B = 34;
  const xs = points.map((p) => p.chatter_change), ys = points.map((p) => p.research_change);
  const pad = (lo: number, hi: number) => {
    const span = Math.max(hi - lo, 40);
    return [Math.floor((lo - span * 0.1) / 20) * 20, Math.ceil((hi + span * 0.1) / 20) * 20];
  };
  const [x0, x1] = pad(Math.min(0, ...xs), Math.max(0, ...xs));
  const [y0, y1] = pad(Math.min(0, ...ys), Math.max(0, ...ys));
  const sx = (v: number) => L + ((v - x0) / (x1 - x0)) * (W - L - R);
  const sy = (v: number) => T + ((y1 - v) / (y1 - y0)) * (H - T - B);
  const ticks = (lo: number, hi: number) => {
    const step = Math.max(20, Math.ceil((hi - lo) / 5 / 20) * 20);
    const out: number[] = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
    return out;
  };
  const placed: { x: number; y: number; w: number }[] = [];
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="분야별 뉴스·커뮤니티 증가율과 논문·오픈소스 증가율">
        {ticks(x0, x1).map((v) => (
          <g key={`x${v}`}>
            <line x1={sx(v)} x2={sx(v)} y1={T} y2={H - B} stroke="var(--border)" />
            <text x={sx(v)} y={H - B + 16} fontSize={11} textAnchor="middle" fill="var(--muted-foreground)">{v}%</text>
          </g>
        ))}
        {ticks(y0, y1).map((v) => (
          <g key={`y${v}`}>
            <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} stroke="var(--border)" />
            <text x={L - 6} y={sy(v) + 4} fontSize={11} textAnchor="end" fill="var(--muted-foreground)">{v}%</text>
          </g>
        ))}
        <line x1={sx(0)} x2={sx(0)} y1={T} y2={H - B} stroke="var(--muted-foreground)" />
        <line x1={L} x2={W - R} y1={sy(0)} y2={sy(0)} stroke="var(--muted-foreground)" />
        {points
          .sort((a, b) => sy(a.research_change) - sy(b.research_change))
          .map((point) => {
            const cx = sx(point.chatter_change), cy = sy(point.research_change);
            const label = FIELD_LABEL[point.key] ?? point.key;
            const width = label.length * 11;
            const clashes = (x: number, y: number) =>
              x < L || x + width > W - R || placed.some((o) => Math.abs(o.x - x) < Math.max(o.w, width) && Math.abs(o.y - y) < 13);
            // right of the dot, else left of it, else nudged down on the right
            let lx = cx + 9, ly = cy + 4;
            if (clashes(lx, ly)) lx = cx - 9 - width;
            if (clashes(lx, ly)) {
              lx = Math.min(cx + 9, W - R - width);
              while (clashes(lx, ly) && ly < H - B) ly += 13;
            }
            placed.push({ x: lx, y: ly, w: width });
            const tip = `${label}: 뉴스·커뮤니티 ${formatChange(point.chatter_change)} (${point.chatter}건), 논문·오픈소스 ${formatChange(point.research_change)} (${point.research}건)`;
            return (
              <g key={point.key}>
                <title>{tip}</title>
                <circle cx={cx} cy={cy} r={12} fill="transparent" />
                <circle cx={cx} cy={cy} r={5} fill="var(--heat)" stroke="var(--card)" strokeWidth={2} />
                <text x={lx} y={ly} fontSize={11.5} fill="var(--foreground)">{label}</text>
              </g>
            );
          })}
      </svg>
      <figcaption className="mt-1 text-xs text-muted-foreground">
        오른쪽 아래일수록 화제는 늘었지만 연구·구현 활동은 따라오지 않은 분야입니다.
        {missing ? ` 직전 기간 0건이라 비교할 수 없는 분야 ${missing}개는 빠졌습니다.` : ""}
      </figcaption>
    </figure>
  );
}

const SHIFT_LANES = [
  { state: "new", title: "새로 등장" },
  { state: "rising", title: "증가" },
  { state: "steady", title: "유지" },
  { state: "falling", title: "감소" },
] as const;

export function KeywordShifts({ radar }: { radar: Radar }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {SHIFT_LANES.map((lane) => {
        const rows = radar.keywords.filter((keyword) => keyword.state === lane.state);
        return (
          <section key={lane.state} className="min-w-0">
            <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
              {lane.title} <span className="tabular-nums">{rows.length}</span>
            </h3>
            {rows.length ? (
              <ul className="space-y-1.5">
                {rows.map((keyword) => (
                  <li key={keyword.key} className="flex items-center gap-2 rounded-md bg-muted px-2.5 py-1.5 text-sm">
                    <Link href={withQuery("/", { q: keyword.label })} className="min-w-0 flex-1 truncate hover:underline">
                      {keyword.label}
                    </Link>
                    <Sparkline values={keyword.counts} width={52} height={16} className={lane.state === "falling" ? "text-impact-risk" : "text-heat"} />
                    <span className="w-8 text-right text-xs text-muted-foreground tabular-nums">{keyword.counts[keyword.counts.length - 1]}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">없음</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
