import type { ReactNode } from "react";

import { formatChange, STATE_META } from "@/lib/radar";
import type { TopicState } from "@/lib/reader-types";
import { cn } from "@/lib/utils";

export function Panel({
  id,
  title,
  question,
  note,
  action,
  children,
  className,
}: {
  id?: string;
  title: string;
  /** The strategy question this view answers, shown under the title. */
  question?: string;
  note?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-title` : undefined} className={cn("min-w-0 scroll-mt-28 rounded-2xl border bg-card p-4 shadow-xs md:p-5", className)}>
      <header className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h2 id={id ? `${id}-title` : undefined} className="text-[15px] font-bold tracking-tight">
            {title}
          </h2>
          {question ? <p className="mt-0.5 text-xs text-muted-foreground">{question}</p> : null}
        </div>
        {action}
      </header>
      {children}
      {note ? <p className="mt-3 border-t pt-2 text-xs leading-relaxed text-muted-foreground">{note}</p> : null}
    </section>
  );
}

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
      className={cn("inline-flex items-center rounded-full px-1.5 py-px text-[11px] font-semibold whitespace-nowrap", STATE_BADGE[state], className)}
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

/** Legend row: a swatch beside text-coloured labels. */
export function Legend({ items, className }: { items: { label: string; swatch: string; shape?: "dot" | "bar" }[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground", className)}>
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span aria-hidden className={cn("inline-block", item.shape === "dot" ? "size-2.5 rounded-full" : "h-2.5 w-3.5 rounded-sm")} style={{ background: item.swatch }} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** "첫 등장" for a keyword first reported in the last three windows, "재등장" for one back after a gap. */
export function KeywordBadge({ topic }: { topic: { debut?: boolean; returning?: boolean } }) {
  if (topic.returning) {
    return <span title="기준 기간 동안 없다가 다시 등장 (그 전에 보도된 적 있음)" className="rounded-full bg-primary/12 px-1.5 py-px text-[11px] font-semibold whitespace-nowrap text-primary">↺ 재등장</span>;
  }
  if (topic.debut) {
    return <span title="최근 3개 기간 안에 처음 보도됨" className="rounded-full bg-primary/12 px-1.5 py-px text-[11px] font-semibold whitespace-nowrap text-primary">✦ 첫 등장</span>;
  }
  return null;
}
