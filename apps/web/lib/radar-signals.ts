/** Signal card types and labels; the cards come from the API. */
import type { Focus } from "@/lib/radar";
import type { Radar } from "@/lib/reader-types";

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

/**
 * The radar's rule-based cards. The rules and their statistics live in the API
 * (apps/api/src/news_insight/public/signals.py, checklist STAT-3·PRD-1) so the digest and the
 * strategy prompts read the same cards; the web only renders them.
 */
export function radarSignals(radar: Radar): Signal[] {
  return (radar.signals ?? [])
    .filter((s): s is typeof s & { tone: SignalTone } => s.tone in SIGNAL_META)
    .map((s) => ({ tone: s.tone, title: s.title, detail: s.detail, focus: s.focus as Focus }));
}
