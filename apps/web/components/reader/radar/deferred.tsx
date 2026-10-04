"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

/**
 * Renders its chart once it nears the viewport, or when the browser is idle (WEB-1), so find-in-page
 * and section links still reach every chart. The server sends a sized placeholder: the first
 * response carries the top of the page and the radar data once, not every chart's SVG.
 */
export function Deferred({ minHeight, children }: { minHeight: number; children: () => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || shown) return;
    if (typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const show = () => setShown(true);
    const idle =
      typeof window.requestIdleCallback === "function"
        ? window.requestIdleCallback(show, { timeout: 4000 })
        : window.setTimeout(show, 2500);
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShown(true);
          observer.disconnect();
        }
      },
      { rootMargin: "800px 0px" },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      if (typeof window.cancelIdleCallback === "function") window.cancelIdleCallback(idle);
      else window.clearTimeout(idle);
    };
  }, [shown]);
  return (
    <div ref={ref} style={shown ? undefined : { minHeight }} aria-busy={!shown}>
      {shown ? children() : <div className="h-full min-h-[inherit] animate-pulse rounded-xl bg-muted/40" />}
    </div>
  );
}
