"use client";

import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/** Reading depth of a briefing (plan 13 C1): one minute, five minutes, everything. */
export type Depth = "one" | "five" | "deep";

export const DEPTHS: { key: Depth; label: string; hint: string }[] = [
  { key: "one", label: "1분", hint: "헤드라인 · 핵심 3줄 · 기업 움직임" },
  { key: "five", label: "5분", hint: "인사이트 카드 · 이어지는 이야기" },
  { key: "deep", label: "심층", hint: "트랙별 기사 · 전체 수집 요약 · 전략 보고서" },
];
const STORAGE_KEY = "briefing-depth";
const DepthContext = createContext<{ depth: Depth; setDepth: (depth: Depth) => void }>({
  depth: "one",
  setDepth: () => undefined,
});

/**
 * Holds the chosen depth (remembered per browser) and exposes it as `data-depth` on a
 * `group/brief` wrapper, so server-rendered sections hide themselves with
 * `group-data-[depth=…]/brief:hidden` without becoming client components.
 */
export function BriefingDepth({ children, className }: { children: ReactNode; className?: string }) {
  const [depth, setDepthState] = useState<Depth>("one");
  useEffect(() => {
    if (window.location.hash === "#summary") {
      setDepthState("deep");
      return;
    }
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "one" || saved === "five" || saved === "deep") setDepthState(saved);
    } catch {
      // storage blocked: keep the default
    }
  }, []);
  const setDepth = (next: Depth) => {
    setDepthState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
  };
  return (
    <DepthContext.Provider value={{ depth, setDepth }}>
      <div data-depth={depth} className={cn("group/brief", className)}>
        {children}
      </div>
    </DepthContext.Provider>
  );
}

export function DepthToggle() {
  const { depth, setDepth } = useContext(DepthContext);
  return (
    <div role="radiogroup" aria-label="읽기 깊이" className="inline-flex rounded-full border bg-background p-0.5">
      {DEPTHS.map((option) => (
        <button
          key={option.key}
          type="button"
          role="radio"
          aria-checked={depth === option.key}
          aria-label={option.label}
          title={option.hint}
          onClick={() => setDepth(option.key)}
          className={cn(
            "rounded-full px-3 py-0.5 text-xs font-medium transition-colors",
            depth === option.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
