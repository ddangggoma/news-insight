import {
  BASELINE_UNIT,
  type Focus,
  formatZ,
  keywordIndex,
  koreaGaps,
  last,
  mean,
  researchShare,
  STATE_META,
  topicLabel,
} from "@/lib/radar";
import type { Radar, Topic, TrackMix } from "@/lib/reader-types";
import { FIELD_LABEL } from "@/lib/taxonomy";

export type SignalTone = "surge" | "event" | "new" | "back" | "early" | "pull" | "shift" | "hype" | "thin" | "gap" | "link" | "cool";

export type Signal = { tone: SignalTone; title: string; detail: string; focus: Focus };

export const SIGNAL_META: Record<SignalTone, { label: string }> = {
  surge: { label: "급상승" },
  event: { label: "이례적인 날" },
  new: { label: "신규 기술" },
  back: { label: "재등장" },
  early: { label: "연구 선행" },
  pull: { label: "개발자 반응 선행" },
  shift: { label: "상용화 이동" },
  hype: { label: "화제 과열" },
  thin: { label: "검증 필요" },
  gap: { label: "국내 공백" },
  link: { label: "융합 신호" },
  cool: { label: "관심 감소" },
};

const chatter = (mix: TrackMix) => mix.news + mix.community;
const research = (mix: TrackMix) => mix.research_ip + mix.oss;
const total = (mix: TrackMix) => chatter(mix) + research(mix);
const pct = (share: number) => `${Math.round(share * 100)}%`;

function top<T>(items: T[], score: (item: T) => number): T | undefined {
  return [...items].sort((a, b) => score(b) - score(a))[0];
}

/** "9/24" from an ISO date. */
function shortDay(iso: string): string {
  const [, month, day] = iso.slice(0, 10).split("-");
  return `${Number(month)}/${Number(day)}`;
}

/**
 * Rule-based reading of the radar: the few things a strategy reader should look at first.
 * Each rule yields at most one signal and each theme appears on one card at most; thresholds
 * keep single-report noise out. Track comparisons use the average of the baseline windows,
 * not the single previous window, which is too noisy at these counts.
 */
export function radarSignals(radar: Radar): Signal[] {
  const themes = radar.themes.filter((t) => last(t.counts) > 0 || mean(t.counts.slice(0, -1)) > 0);
  const history = radar.periods.length - 1;
  const baseline = `직전 ${history}${BASELINE_UNIT[radar.window.kind]}`;
  const perWindow = (mix: TrackMix, pick: (m: TrackMix) => number) => pick(mix) / Math.max(history, 1);
  const signals: Signal[] = [];
  const theme = (t: Topic): Focus => ({ kind: "theme", key: t.key });
  const used = new Set<string>();
  const unused = (rows: Topic[]) => rows.filter((t) => !used.has(t.key));
  const push = (signal: Signal) => {
    signals.push(signal);
    used.add(signal.focus.key);
  };

  const surge = top(
    themes.filter((t) => t.state === "surging"),
    (t) => t.z,
  );
  if (surge) {
    push({
      tone: "surge",
      title: topicLabel("theme", surge),
      detail: `${last(surge.counts)}건, ${baseline} 평균 ${mean(surge.counts.slice(0, -1)).toFixed(1)}건 대비 ${formatZ(surge.z)} · 출처 ${surge.sources}곳`,
      focus: theme(surge),
    });
  }

  // the busiest anomaly day inside the current window: a launch, an announcement, an incident
  const windowStart = radar.window.start.slice(0, 10);
  const event = top(
    radar.calendar.anomalies.filter((a) => a.day >= windowStart),
    (a) => a.z,
  );
  if (event) {
    const words = event.keywords.map((k) => k.label);
    push({
      tone: "event",
      title: `${shortDay(event.day)} ${FIELD_LABEL[event.field] ?? event.field}`,
      detail: `하루 ${event.count}건, 평소 같은 요일 ${event.expected.toFixed(1)}건의 ${(event.count / Math.max(event.expected, 1)).toFixed(1)}배${words.length ? ` · ${words.join(", ")}` : ""}`,
      focus: event.keywords[0] ? { kind: "keyword", key: event.keywords[0].key } : { kind: "field", key: event.field },
    });
  }

  const fresh = radar.keywords
    .filter((k) => !k.returning && (k.state === "new" || (k.debut && k.state !== "falling")))
    .sort((a, b) => last(b.counts) - last(a.counts) || b.z - a.z);
  if (fresh.length) {
    const lead = fresh[0];
    const others = fresh.slice(1, 4).map((k) => topicLabel("keyword", k));
    push({
      tone: "new",
      title: topicLabel("keyword", lead),
      detail: `처음 보도된 지 ${daysSince(lead.first_ever, radar)}일, 이번 기간 ${last(lead.counts)}건 · 출처 ${lead.sources}곳${others.length ? ` · 함께 등장: ${others.join(", ")}` : ""}`,
      focus: { kind: "keyword", key: lead.key },
    });
  }

  const back = top(
    radar.keywords.filter((k) => k.returning),
    (k) => last(k.counts),
  );
  if (back) {
    push({
      tone: "back",
      title: topicLabel("keyword", back),
      detail: `${baseline} 동안 없다가 ${last(back.counts)}건 · 첫 보도는 ${daysSince(back.first_ever, radar)}일 전: 다시 주목받는 이유 확인`,
      focus: { kind: "keyword", key: back.key },
    });
  }

  const early = top(
    unused(themes).filter((t) => last(t.counts) >= 3 && t.z >= 1 && (researchShare(t.tracks) ?? 0) >= 0.5),
    (t) => t.z * (researchShare(t.tracks) ?? 0),
  );
  if (early) {
    push({
      tone: "early",
      title: topicLabel("theme", early),
      detail: `논문·오픈소스 비중 ${pct(researchShare(early.tracks) ?? 0)}, ${formatZ(early.z)}: 시장 보도보다 연구·구현이 앞서는 초기 단계`,
      focus: theme(early),
    });
  }

  // reactions (stars, points) far ahead of how often the theme is written about
  const mentions = themes.reduce((sum, t) => sum + last(t.counts), 0);
  const reactions = radar.engagement.themes.reduce((sum, t) => sum + t.score, 0);
  const byKey = new Map(themes.map((t) => [t.key, t]));
  // ranked by the share of reactions beyond the share of mentions, so a tiny theme with a
  // high ratio does not beat a large one far above the line
  const excess = (e: { key: string; score: number }) => e.score / reactions - last(byKey.get(e.key)!.counts) / mentions;
  const pull = top(
    radar.engagement.themes.filter((e) => {
      const t = byKey.get(e.key);
      return !!t && !used.has(t.key) && e.items >= 5 && mentions > 0 && reactions > 0 && e.score / reactions >= (2 * last(t.counts)) / mentions;
    }),
    excess,
  );
  if (pull) {
    const t = byKey.get(pull.key)!;
    push({
      tone: "pull",
      title: topicLabel("theme", t),
      detail: `언급 비중 ${pct(last(t.counts) / mentions)}인데 반응(스타·포인트 증가) 비중 ${pct(pull.score / reactions)} · ${pull.items}건: 개발자 채택이 보도보다 앞섬`,
      focus: theme(t),
    });
  }

  // the research share fell: a two-proportion z-test keeps small counts from winning
  const shift = top(
    unused(themes).filter((t) => total(t.tracks) >= 5 && total(t.baseline_tracks) >= 10 && shareDrop(t) >= 0.2 && shareDropZ(t) >= 2),
    shareDropZ,
  );
  if (shift) {
    const before = researchShare(shift.baseline_tracks) ?? 0;
    const now = researchShare(shift.tracks) ?? 0;
    push({
      tone: "shift",
      title: topicLabel("theme", shift),
      detail: `논문·오픈소스 비중 ${baseline} ${pct(before)} → 이번 ${pct(now)}: 연구에서 제품·시장 이야기로 넘어가는 중`,
      focus: theme(shift),
    });
  }

  const hype = top(
    unused(themes).filter((t) => {
      const usual = perWindow(t.baseline_tracks, chatter);
      const usualResearch = perWindow(t.baseline_tracks, research);
      return chatter(t.tracks) >= 5 && usual > 0 && chatter(t.tracks) >= usual * 1.5 && research(t.tracks) <= usualResearch * 1.1;
    }),
    (t) => chatter(t.tracks) / Math.max(perWindow(t.baseline_tracks, chatter), 0.5),
  );
  if (hype) {
    const usual = perWindow(hype.baseline_tracks, chatter);
    push({
      tone: "hype",
      title: topicLabel("theme", hype),
      detail: `뉴스·커뮤니티 ${chatter(hype.tracks)}건으로 평소(${usual.toFixed(1)}건)의 ${(chatter(hype.tracks) / usual).toFixed(1)}배, 논문·오픈소스는 ${research(hype.tracks)}건(평소 ${perWindow(hype.baseline_tracks, research).toFixed(1)}건): 화제가 실체보다 앞섬`,
      focus: theme(hype),
    });
  }

  // a rise carried by one or two outlets, or by vendors' own newsrooms
  const thin = top(
    unused(themes).filter((t) => {
      const narrow = t.effective_sources !== null && t.effective_sources < 2.5;
      const vendor = t.tracks.news >= 4 && t.official / t.tracks.news >= 0.5;
      return last(t.counts) >= 5 && t.z >= 1 && (narrow || vendor);
    }),
    (t) => t.z,
  );
  if (thin) {
    const parts = [
      thin.effective_sources !== null ? `실효 출처 ${thin.effective_sources.toFixed(1)}곳` : "",
      thin.official && thin.tracks.news ? `뉴스 중 공식 발표 ${pct(thin.official / thin.tracks.news)}` : "",
    ].filter(Boolean);
    push({
      tone: "thin",
      title: topicLabel("theme", thin),
      detail: `${last(thin.counts)}건, ${formatZ(thin.z)} 상승이지만 ${parts.join(" · ")}: 독립 보도로 확인 필요`,
      focus: theme(thin),
    });
  }

  const gap = koreaGaps(radar, 3);
  if (gap.length) {
    const lead = gap[0];
    const others = gap.slice(1).map((k) => topicLabel("keyword", k));
    push({
      tone: "gap",
      title: topicLabel("keyword", lead),
      detail: `해외 ${last(lead.counts)}건${lead.state ? ` · ${STATE_META[lead.state].label}` : ""}, 국내 출처 0건${others.length ? ` · 같은 상황: ${others.join(", ")}` : ""}`,
      focus: { kind: "keyword", key: lead.key },
    });
  }

  const keywords = keywordIndex(radar);
  const crossField = (a: string, b: string) => {
    const fa = keywords.get(a)?.field, fb = keywords.get(b)?.field;
    return !!fa && !!fb && fa !== fb;
  };
  const link = top(
    radar.pairs.filter((p) => p.lift >= 2 && (p.is_new || crossField(p.a, p.b))),
    (p) => (p.is_new ? 1000 : 0) + (crossField(p.a, p.b) ? 500 : 0) + p.count * p.lift,
  );
  const fieldLink = top(
    radar.field_links.filter((l) => l.previous === 0 && l.count >= 3),
    (l) => l.count,
  );
  if (link) {
    const a = keywords.get(link.a), b = keywords.get(link.b);
    const fields = [a?.field, b?.field].filter((f): f is string => !!f && f in FIELD_LABEL);
    push({
      tone: "link",
      title: `${a ? topicLabel("keyword", a) : link.a} × ${b ? topicLabel("keyword", b) : link.b}`,
      detail: `함께 언급 ${link.count}건, 우연 대비 ${link.lift.toFixed(1)}배${link.is_new ? " · 이번 기간 첫 동시 언급" : ""}${new Set(fields).size === 2 ? ` · ${fields.map((f) => FIELD_LABEL[f]).join("↔")}` : ""}`,
      focus: { kind: "keyword", key: link.a },
    });
  } else if (fieldLink) {
    push({
      tone: "link",
      title: `${FIELD_LABEL[fieldLink.a]} × ${FIELD_LABEL[fieldLink.b]}`,
      detail: `두 카테고리에 함께 분류된 보도 ${fieldLink.count}건, 직전 기간 0건: 새로 생긴 교차점`,
      focus: { kind: "field", key: fieldLink.a },
    });
  }

  const cool = top(
    unused(themes).filter((t) => t.state === "falling"),
    (t) => -t.z,
  );
  if (cool) {
    push({
      tone: "cool",
      title: topicLabel("theme", cool),
      detail: `${last(cool.counts)}건, ${baseline} 평균 ${mean(cool.counts.slice(0, -1)).toFixed(1)}건 대비 ${formatZ(cool.z)}`,
      focus: theme(cool),
    });
  }
  return signals;
}

function shareDrop(t: Topic): number {
  return (researchShare(t.baseline_tracks) ?? 0) - (researchShare(t.tracks) ?? 0);
}

/** z of the drop in research share between the baseline and the current window. */
export function shareDropZ(t: Topic): number {
  const n1 = total(t.baseline_tracks), n2 = total(t.tracks);
  if (!n1 || !n2) return 0;
  const pooled = (research(t.baseline_tracks) + research(t.tracks)) / (n1 + n2);
  const se = Math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2));
  return se ? shareDrop(t) / se : 0;
}

/** Whole days from a keyword's first report to the end of the radar window. */
function daysSince(iso: string | null | undefined, radar: Radar): number {
  if (!iso) return 0;
  const windowEnd = Date.parse(radar.window.end);
  const end = Number.isNaN(windowEnd) ? Date.now() : Math.min(windowEnd, Date.now());
  return Math.max(0, Math.floor((end - Date.parse(iso)) / 86_400_000));
}
