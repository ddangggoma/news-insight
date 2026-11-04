import { formatChange, STATE_META } from "@/lib/radar";
import type { TopicState } from "@/lib/reader-types";
import { cn } from "@/lib/utils";

// chart panels and legends carry the chart tools (zoom, full screen, series toggles)
export { ChartPanel as Panel, Legend } from "@/components/chart-frame";

const STATE_BADGE: Record<TopicState, string> = {
  new: "bg-primary/12 text-primary",
  surging: "bg-state-hot/14 text-state-hot",
  rising: "bg-state-hot/8 text-state-hot",
  steady: "bg-muted text-ink-2",
  falling: "bg-state-cool/12 text-state-cool",
};

export function StateBadge({ state, className }: { state: TopicState | null; className?: string }) {
  if (!state) return null;
  return (
    <span
      title={STATE_META[state].hint}
      className={cn("inline-flex items-center rounded-full px-1.5 py-px text-xs font-semibold whitespace-nowrap", STATE_BADGE[state], className)}
    >
      {state === "surging" ? "▲▲ " : state === "rising" ? "▲ " : state === "falling" ? "▼ " : state === "new" ? "● " : ""}
      {STATE_META[state].label}
    </span>
  );
}

export function Change({ value, className }: { value: number | null; className?: string }) {
  return (
    <span
      className={cn(
        "tabular-nums",
        value === null ? "text-muted-foreground" : value >= 0 ? "text-impact-opportunity" : "text-impact-risk",
        className,
      )}
    >
      {formatChange(value)}
    </span>
  );
}

/** "첫 등장" for a keyword first reported in the last three windows, "재등장" for one back after a gap. */
export function KeywordBadge({ topic }: { topic: { debut?: boolean; returning?: boolean } }) {
  if (topic.returning) {
    return <span title="기준 기간 동안 없다가 다시 등장 (그 전에 보도된 적 있음)" className="rounded-full bg-primary/12 px-1.5 py-px text-xs font-semibold whitespace-nowrap text-primary">↺ 재등장</span>;
  }
  if (topic.debut) {
    return <span title="최근 3개 기간 안에 처음 보도됨" className="rounded-full bg-primary/12 px-1.5 py-px text-xs font-semibold whitespace-nowrap text-primary">✦ 첫 등장</span>;
  }
  return null;
}
