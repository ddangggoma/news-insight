import {
  BASELINE_UNIT,
  type Focus,
  formatChange,
  formatZ,
  keywordIndex,
  last,
  mean,
  researchShare,
  topicLabel,
} from "@/lib/radar";
import type { Radar, Topic, TrackMix } from "@/lib/reader-types";
import { FIELD_LABEL } from "@/lib/taxonomy";

export type SignalTone = "surge" | "new" | "early" | "shift" | "hype" | "link" | "cool";

export type Signal = { tone: SignalTone; title: string; detail: string; focus: Focus };

export const SIGNAL_META: Record<SignalTone, { label: string }> = {
  surge: { label: "급상승" },
  new: { label: "신규 기술" },
  early: { label: "연구 선행" },
  shift: { label: "상용화 이동" },
  hype: { label: "화제 과열" },
  link: { label: "융합 신호" },
  cool: { label: "관심 감소" },
};

const chatter = (mix: TrackMix) => mix.news + mix.community;
const research = (mix: TrackMix) => mix.research_ip + mix.oss;
const pct = (share: number) => `${Math.round(share * 100)}%`;

function baseline(radar: Radar): string {
  return `직전 ${radar.periods.length - 1}${BASELINE_UNIT[radar.window.kind]}`;
}

function top<T>(items: T[], score: (item: T) => number): T | undefined {
  return [...items].sort((a, b) => score(b) - score(a))[0];
}

/**
 * Rule-based reading of the radar: the few things a strategy reader should look at first.
 * Each rule yields at most one signal; thresholds keep single-report noise out.
 */
export function radarSignals(radar: Radar): Signal[] {
  const themes = radar.themes.filter((t) => last(t.counts) > 0 || mean(t.counts.slice(0, -1)) > 0);
  const signals: Signal[] = [];
  const theme = (t: Topic): Focus => ({ kind: "theme", key: t.key });
  // one card per theme: a theme already named by an earlier rule is skipped by later ones
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
      detail: `${last(surge.counts)}건, ${baseline(radar)} 평균 ${mean(surge.counts.slice(0, -1)).toFixed(1)}건 대비 ${formatZ(surge.z)} · 출처 ${surge.sources}곳`,
      focus: theme(surge),
    });
  }

  const fresh = radar.keywords.filter((k) => k.state === "new").sort((a, b) => last(b.counts) - last(a.counts));
  if (fresh.length) {
    const lead = fresh[0];
    const others = fresh.slice(1, 4).map((k) => topicLabel("keyword", k));
    push({
      tone: "new",
      title: topicLabel("keyword", lead),
      detail: `${baseline(radar)} 동안 없던 기술이 ${last(lead.counts)}건, 출처 ${lead.sources}곳에서 등장${others.length ? ` · 함께 등장: ${others.join(", ")}` : ""}`,
      focus: { kind: "keyword", key: lead.key },
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

  const shift = top(
    unused(themes).filter((t) => sumOf(t.tracks) >= 5 && sumOf(t.previous_tracks) >= 5),
    (t) => (researchShare(t.previous_tracks) ?? 0) - (researchShare(t.tracks) ?? 0),
  );
  if (shift) {
    const before = researchShare(shift.previous_tracks) ?? 0;
    const now = researchShare(shift.tracks) ?? 0;
    if (before - now >= 0.2) {
      push({
        tone: "shift",
        title: topicLabel("theme", shift),
        detail: `논문·오픈소스 비중 ${pct(before)} → ${pct(now)}: 연구에서 제품·시장 이야기로 넘어가는 중`,
        focus: theme(shift),
      });
    }
  }

  const hype = top(
    unused(themes).filter((t) => {
      const growth = changeOf(chatter(t.tracks), chatter(t.previous_tracks));
      const flat = research(t.previous_tracks) >= 1 && research(t.tracks) <= research(t.previous_tracks);
      return chatter(t.tracks) >= 5 && growth !== null && growth >= 50 && flat;
    }),
    (t) => changeOf(chatter(t.tracks), chatter(t.previous_tracks)) ?? 0,
  );
  if (hype) {
    push({
      tone: "hype",
      title: topicLabel("theme", hype),
      detail: `뉴스·커뮤니티 ${formatChange(changeOf(chatter(hype.tracks), chatter(hype.previous_tracks)))}, 논문·오픈소스 ${formatChange(changeOf(research(hype.tracks), research(hype.previous_tracks)))}: 화제가 실체보다 앞섬`,
      focus: theme(hype),
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
  if (link) {
    const a = keywords.get(link.a), b = keywords.get(link.b);
    const fields = [a?.field, b?.field].filter((f): f is string => !!f && f in FIELD_LABEL);
    push({
      tone: "link",
      title: `${a ? topicLabel("keyword", a) : link.a} × ${b ? topicLabel("keyword", b) : link.b}`,
      detail: `함께 언급 ${link.count}건, 우연 대비 ${link.lift.toFixed(1)}배${link.is_new ? " · 이번 기간 첫 동시 언급" : ""}${new Set(fields).size === 2 ? ` · ${fields.map((f) => FIELD_LABEL[f]).join("↔")}` : ""}`,
      focus: { kind: "keyword", key: link.a },
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
      detail: `${last(cool.counts)}건, ${baseline(radar)} 평균 ${mean(cool.counts.slice(0, -1)).toFixed(1)}건 대비 ${formatZ(cool.z)}`,
      focus: theme(cool),
    });
  }
  return signals;
}

function sumOf(mix: TrackMix): number {
  return chatter(mix) + research(mix);
}

function changeOf(count: number, previous: number): number | null {
  return previous ? ((count - previous) / previous) * 100 : null;
}
