"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChartTips } from "@/components/reader/radar/chart-tips";
import { Change, Legend, StateBadge } from "@/components/reader/radar/parts";
import { COMPANY_SIGNAL_LABEL, RELATION_META } from "@/lib/companies";
import { withQuery } from "@/lib/query";
import { formatPoints, formatZ, last, radarFilters, radarHref, type Focus, type RadarView, signalLabel } from "@/lib/radar";
import type { CompanyRadar, CompanyRelation, CompanyTopic, Radar } from "@/lib/reader-types";
import { THEME_LABEL } from "@/lib/taxonomy";
import { cn } from "@/lib/utils";

const ROWS = 15;
const LEADER_THEMES = 8;

function RelationBadge({ relation }: { relation: CompanyRelation }) {
  const meta = RELATION_META[relation];
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
      <span aria-hidden className="size-2 rounded-full" style={{ background: meta.color }} />
      {meta.label}
    </span>
  );
}

/** Reports from other outlets: a busy newsroom is not news. */
function external(topic: CompanyTopic): number {
  return last(topic.counts) - topic.self_reports;
}

function mainSignal(topic: CompanyTopic): string | null {
  const entries = Object.entries(topic.signal_mix).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries[0][0] : null;
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-xs font-semibold text-ink-2">{children}</h3>;
}

function MomentumTable({ rows, at }: { rows: CompanyTopic[]; at: (focus: Focus) => string }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, ROWS);
  return (
    <div className="min-w-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-[11px] text-muted-foreground">
            <tr className="border-b">
              <th className="py-1.5 pr-2 font-medium">기업</th>
              <th className="py-1.5 pr-2 text-right font-medium" title="다른 매체 보도 / 자사 발표">외부 · 자사</th>
              <th className="py-1.5 pr-2 text-right font-medium">직전 대비</th>
              <th className="py-1.5 pr-2 font-medium">상태</th>
              <th className="py-1.5 pr-2 font-medium">주 활동 · 전환</th>
              <th className="py-1.5 font-medium">많이 다뤄진 테마</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((topic) => {
              const main = mainSignal(topic);
              return (
                <tr key={topic.key} className="border-b border-border/60 align-top">
                  <td className="py-1.5 pr-2">
                    <Link href={at({ kind: "company", key: topic.key })} scroll={false} className="font-semibold hover:text-primary">
                      {topic.label ?? topic.name}
                    </Link>
                    <div>
                      <RelationBadge relation={topic.relation} />
                    </div>
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">
                    <b>{external(topic)}</b>
                    {topic.self_reports ? <span className="text-muted-foreground"> · {topic.self_reports}</span> : null}
                  </td>
                  <td className="py-1.5 pr-2 text-right">
                    <Change value={topic.change} />
                    <div className="text-[11px] text-muted-foreground tabular-nums">{formatZ(topic.z)}</div>
                  </td>
                  <td className="py-1.5 pr-2">
                    <StateBadge state={topic.state} />
                  </td>
                  <td className="py-1.5 pr-2 text-xs">
                    {main ? signalLabel(main) : "–"}
                    {topic.shift ? (
                      <div className="font-semibold text-state-hot" title={`두 비율 z ${topic.shift.z.toFixed(1)}`}>
                        → {signalLabel(topic.shift.signal_type)} {Math.round(topic.shift.baseline_share * 100)}%→{Math.round(topic.shift.share * 100)}%
                      </div>
                    ) : null}
                  </td>
                  <td className="py-1.5 text-xs">
                    <div className="flex flex-wrap gap-1">
                      {topic.top_themes.map((theme) => (
                        <Link key={theme.key} href={at({ kind: "theme", key: theme.key })} scroll={false} className="rounded bg-muted px-1.5 py-px text-ink-2 hover:text-primary">
                          {THEME_LABEL[theme.key] ?? theme.key} {theme.count}
                        </Link>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows.length > ROWS ? (
        <button type="button" onClick={() => setAll(!all)} className="mt-2 text-xs font-semibold text-primary hover:underline">
          {all ? "접기" : `${rows.length - ROWS}곳 더 보기`}
        </button>
      ) : null}
    </div>
  );
}

function ThemeLeaderList({ data, at }: { data: CompanyRadar; at: (focus: Focus) => string }) {
  const themes = data.theme_leaders.slice(0, LEADER_THEMES);
  if (!themes.length) return <p className="text-sm text-muted-foreground">테마별 기업 보도가 아직 적습니다.</p>;
  return (
    <ul className="space-y-3">
      {themes.map((theme) => (
        <li key={theme.theme}>
          <div className="mb-1 flex items-center justify-between gap-2 text-xs">
            <Link href={at({ kind: "theme", key: theme.theme })} scroll={false} className="font-semibold hover:text-primary">
              {THEME_LABEL[theme.theme] ?? theme.theme}
            </Link>
            <span className="text-muted-foreground tabular-nums">
              {theme.leader_changed ? <span className="mr-1.5 rounded-full bg-state-hot/14 px-1.5 py-px font-semibold text-state-hot">리더 교체</span> : null}
              기업 보도 {theme.total}건
            </span>
          </div>
          <ul className="space-y-0.5">
            {theme.leaders.map((leader) => (
              <li key={leader.key} className="grid grid-cols-[7rem_minmax(0,1fr)_7.5rem] items-center gap-2 text-xs" data-tip={`${leader.label}\n${leader.count}건 · ${leader.share}%${leader.previous_share !== null ? `\n직전 ${leader.previous_share}%` : ""}`}>
                <Link href={at({ kind: "company", key: leader.key })} scroll={false} className="truncate hover:text-primary">
                  {leader.label}
                </Link>
                <span className="h-2 overflow-hidden rounded-sm bg-muted">
                  <span className="block h-full rounded-sm bg-primary/70" style={{ width: `${Math.min(leader.share, 100)}%` }} />
                </span>
                <span className="text-right whitespace-nowrap tabular-nums">
                  {leader.share.toFixed(0)}%
                  {leader.previous_share !== null ? (
                    <span className={cn("ml-1", leader.share >= leader.previous_share ? "text-impact-opportunity" : "text-impact-risk")}>
                      {formatPoints(leader.share - leader.previous_share)}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

/** Competitors: launches (x) against the share of reports read as a risk to DX (y). */
function CompetitorPressure({ rows, at }: { rows: CompanyTopic[]; at: (focus: Focus) => string }) {
  const competitors = rows.filter((t) => t.relation === "competitor" && last(t.counts) > 0);
  if (!competitors.length) return <p className="text-sm text-muted-foreground">이번 기간 경쟁사 보도가 없습니다.</p>;
  const W = 360, H = 220, P = 28;
  const maxX = Math.max(...competitors.map((t) => t.signal_mix.launch ?? 0), 1);
  const maxN = Math.max(...competitors.map((t) => last(t.counts)), 1);
  const labelled = new Set([...competitors].sort((a, b) => last(b.counts) - last(a.counts)).slice(0, 6).map((t) => t.key));
  const x = (v: number) => P + (v / maxX) * (W - P * 2);
  const y = (share: number) => H - P - share * (H - P * 2);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="경쟁사 출시 건수와 위험 비중">
      <line x1={P} x2={W - P} y1={H - P} y2={H - P} stroke="var(--border)" />
      <line x1={P} x2={P} y1={P} y2={H - P} stroke="var(--border)" />
      <line x1={P} x2={W - P} y1={y(0.5)} y2={y(0.5)} stroke="var(--border)" strokeDasharray="3 3" />
      <text x={W - P} y={H - 8} fontSize={10} textAnchor="end" fill="var(--muted-foreground)">출시 보도 →</text>
      <text x={4} y={P - 8} fontSize={10} fill="var(--muted-foreground)">위험 비중 ↑</text>
      {competitors.map((topic) => {
        const count = last(topic.counts);
        const launches = topic.signal_mix.launch ?? 0;
        const risk = count ? topic.impacts.risk / count : 0;
        const r = 4 + 10 * Math.sqrt(count / maxN);
        return (
          <Link key={topic.key} href={at({ kind: "company", key: topic.key })} scroll={false}>
            <g data-tip={`${topic.label ?? topic.name}\n출시 ${launches}건 · 위험 ${Math.round(risk * 100)}% · 전체 ${count}건`}>
              <circle cx={x(launches)} cy={y(risk)} r={r} fill="var(--impact-risk)" fillOpacity={0.25} stroke="var(--impact-risk)" />
              {labelled.has(topic.key) ? (
                <text x={x(launches)} y={y(risk) - r - 3} fontSize={10} textAnchor="middle" fill="var(--foreground)" paintOrder="stroke" stroke="var(--card)" strokeWidth={3}>
                  {topic.label ?? topic.name}
                </text>
              ) : null}
            </g>
          </Link>
        );
      })}
    </svg>
  );
}

function Lists({ data, at }: { data: CompanyRadar; at: (focus: Focus) => string }) {
  const name = (key: string) => [...data.companies, ...data.organizations].find((t) => t.key === key)?.label ?? key;
  return (
    <div className="grid gap-5 md:grid-cols-3 [&>*]:min-w-0">
      <div>
        <Heading>신흥 업체</Heading>
        {data.entrants.length ? (
          <ul className="space-y-1.5 text-sm">
            {data.entrants.map((entrant) => (
              <li key={entrant.key} className="flex items-baseline justify-between gap-2">
                <Link href={entrant.registered ? at({ kind: "company", key: entrant.key }) : withQuery("/", { q: entrant.name })} scroll={!entrant.registered} className="truncate font-medium hover:text-primary">
                  {entrant.name}
                  {entrant.registered ? null : <span className="ml-1 rounded bg-muted px-1 text-[10px] text-muted-foreground">미등록</span>}
                </Link>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {entrant.cards}건 · {entrant.sources}곳
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">기준 기간에 없던 업체가 없습니다.</p>
        )}
      </div>
      <div>
        <Heading>새 테마 진입</Heading>
        {data.entries.length ? (
          <ul className="space-y-1.5 text-sm">
            {data.entries.map((entry) => (
              <li key={`${entry.key}-${entry.theme}`}>
                <Link href={at({ kind: "company", key: entry.key })} scroll={false} className="font-medium hover:text-primary">
                  {entry.label}
                </Link>
                <span className="text-muted-foreground"> → </span>
                <Link href={at({ kind: "theme", key: entry.theme })} scroll={false} className="hover:text-primary">
                  {THEME_LABEL[entry.theme] ?? entry.theme}
                </Link>
                <span className="ml-1 text-xs text-muted-foreground tabular-nums">
                  {entry.count}건 · {entry.sources}곳
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">주력 테마 밖으로 처음 나간 기업이 없습니다.</p>
        )}
      </div>
      <div>
        <Heading>함께 언급된 기업</Heading>
        {data.pairs.length ? (
          <ul className="space-y-1.5 text-sm">
            {data.pairs.slice(0, 10).map((pair) => (
              <li key={`${pair.a}-${pair.b}`} className="flex items-baseline justify-between gap-2">
                <span className="truncate">
                  <Link href={at({ kind: "company", key: pair.a })} scroll={false} className="hover:text-primary">
                    {name(pair.a)}
                  </Link>
                  {" × "}
                  <Link href={at({ kind: "company", key: pair.b })} scroll={false} className="hover:text-primary">
                    {name(pair.b)}
                  </Link>
                  {pair.is_new ? <span className="ml-1 rounded-full bg-primary/12 px-1.5 text-[10px] font-semibold text-primary">새 조합</span> : null}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {pair.count}건 · {pair.lift.toFixed(1)}배{pair.signal_type ? ` · ${signalLabel(pair.signal_type)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">함께 언급된 기업 쌍이 없습니다.</p>
        )}
      </div>
    </div>
  );
}

/**
 * Company radar (plan 12): fetched separately from the radar so the radar page stays light.
 * Ranks by reports from other outlets; self-announced reports (the company's own domains) are
 * shown beside them.
 */
export function CompanyBoard({ radar, view }: { radar: Radar; view: RadarView }) {
  const [data, setData] = useState<CompanyRadar | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<"companies" | "organizations">("companies");
  const { scope, signal, field } = view;

  useEffect(() => {
    const controller = new AbortController();
    const query = radarFilters({ scope, signal, field, focus: null });
    fetch(withQuery(`/radar/${radar.window.kind}/${radar.window.key}/companies`, query), { signal: controller.signal })
      .then((response) => (response.ok ? (response.json() as Promise<CompanyRadar>) : Promise.reject(new Error(String(response.status)))))
      .then((next) => {
        setData(next);
        setFailed(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [radar.window.kind, radar.window.key, scope, signal, field]);

  if (failed) return <p className="text-sm text-muted-foreground">기업 레이더를 불러오지 못했습니다.</p>;
  if (!data) return <div className="h-[520px] animate-pulse rounded-xl bg-muted/40" aria-busy />;

  const at = (focus: Focus) => radarHref(radar.window.kind, radar.window.key, { ...view, focus });
  const history = data.tagged.slice(0, -1).filter((n) => n > 0).length >= (data.tagged.length - 1) / 2;
  const rows = tab === "companies" ? data.companies : data.organizations;

  return (
    <ChartTips className="space-y-5">
      {data.signals.length ? (
        <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" aria-label="기업 신호">
          {data.signals.map((s) => (
            <li key={s.tone}>
              <Link
                href={s.focus.kind === "search" ? withQuery("/", { q: s.focus.key }) : at({ kind: "company", key: s.focus.key })}
                scroll={s.focus.kind === "search"}
                className="block h-full rounded-xl border bg-background p-3 transition hover:border-primary/40"
              >
                <span className="block text-[11px] font-semibold text-muted-foreground">{COMPANY_SIGNAL_LABEL[s.tone] ?? s.tone}</span>
                <span className="block font-bold leading-snug">{s.title}</span>
                <span className="mt-0.5 block text-xs text-ink-2">{s.detail}</span>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <p role="note" className="rounded-xl border border-dashed px-3 py-2 text-xs text-muted-foreground">
          {history
            ? "이번 기간에는 기준을 넘는 기업 신호가 없습니다."
            : `기업 태그가 붙은 보도가 아직 ${data.tagged.filter((n) => n > 0).length}개 기간뿐입니다. 이전 기간이 쌓이면 급부상·활동 전환·새 테마 진입·신흥 업체 신호가 켜집니다.`}
        </p>
      )}

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div role="tablist" aria-label="기업 · 기관" className="flex gap-1">
            {(
              [
                ["companies", `기업 ${data.companies.length}`],
                ["organizations", `기관·단체 ${data.organizations.length}`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={cn("rounded-full px-3 py-1 text-xs font-medium", tab === key ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground")}
              >
                {label}
              </button>
            ))}
          </div>
          <Legend items={(Object.keys(RELATION_META) as CompanyRelation[]).map((r) => ({ label: RELATION_META[r].label, swatch: RELATION_META[r].color, shape: "dot" }))} />
        </div>
        <MomentumTable rows={rows} at={at} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] [&>*]:min-w-0">
        <div>
          <Heading>테마별 점유 · 리더 교체 (자사 발표 제외)</Heading>
          <ThemeLeaderList data={data} at={at} />
        </div>
        <div>
          <Heading>경쟁사 압력 (출시 보도 × 위험 비중)</Heading>
          <CompetitorPressure rows={data.companies} at={at} />
        </div>
      </div>

      <Lists data={data} at={at} />
    </ChartTips>
  );
}
