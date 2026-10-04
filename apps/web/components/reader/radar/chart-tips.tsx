"use client";

import { type ReactNode, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type Tip = { lines: string[]; x: number; y: number };

/**
 * One tooltip for every mark inside: any element with `data-tip` ("title\nvalue\nmore…") shows it
 * on hover and keyboard focus. Text is rendered as React text, never as HTML.
 */
export function ChartTips({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  function show(target: EventTarget | null, clientX?: number, clientY?: number) {
    const host = ref.current;
    const mark = target instanceof Element ? target.closest("[data-tip]") : null;
    if (!host || !mark || !host.contains(mark)) return setTip(null);
    const box = host.getBoundingClientRect();
    const markBox = mark.getBoundingClientRect();
    const x = (clientX ?? markBox.left + markBox.width / 2) - box.left;
    const y = (clientY ?? markBox.top) - box.top;
    setTip({ lines: (mark.getAttribute("data-tip") ?? "").split("\n"), x, y });
  }

  const width = ref.current?.clientWidth ?? 0;
  return (
    <div
      ref={ref}
      className={cn("relative", className)}
      onPointerMove={(event) => show(event.target, event.clientX, event.clientY)}
      onPointerLeave={() => setTip(null)}
      onFocus={(event) => show(event.target)}
      onBlur={() => setTip(null)}
    >
      {children}
      {tip ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-20 w-max max-w-64 rounded-lg border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur"
          style={{
            left: Math.min(Math.max(tip.x + 12, 0), Math.max(width - 200, 0)),
            top: tip.y + 14,
          }}
        >
          <div className="text-muted-foreground">{tip.lines[0]}</div>
          {tip.lines[1] ? <div className="text-sm font-semibold text-foreground tabular-nums">{tip.lines[1]}</div> : null}
          {tip.lines.slice(2).map((line) => (
            <div key={line} className="text-ink-2">
              {line}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
