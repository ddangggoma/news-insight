"use client";

import { useEffect, useRef } from "react";

/** On narrow screens the topic panel sits above the charts: bring it into view when the focus changes. */
export function FocusScroll({ focusKey, children }: { focusKey: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (window.matchMedia("(max-width: 1023px)").matches) ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focusKey]);
  return (
    <div ref={ref} className="scroll-mt-20">
      {children}
    </div>
  );
}
