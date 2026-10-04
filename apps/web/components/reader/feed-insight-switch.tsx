"use client";

import { type ReactNode, useState } from "react";

import { cn } from "@/lib/utils";

/** Below 768px the feed and the insight panel share one column as two tabs. */
export function FeedInsightSwitch({ feed, insight }: { feed: ReactNode; insight: ReactNode }) {
  const [tab, setTab] = useState<"feed" | "insight">("feed");
  return (
    <>
      <div role="tablist" aria-label="보기" className="flex border-b md:hidden">
        {(["feed", "insight"] as const).map((value) => (
          <button
            key={value}
            role="tab"
            type="button"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              "flex-1 py-2.5 text-sm text-muted-foreground",
              tab === value && "font-semibold text-primary shadow-[inset_0_-2px_0] shadow-primary",
            )}
          >
            {value === "feed" ? "피드" : "인사이트"}
          </button>
        ))}
      </div>
      <div className={cn("min-w-0", tab !== "feed" && "hidden md:block")}>{feed}</div>
      <div className={cn("min-w-0", tab !== "insight" && "hidden md:block")}>{insight}</div>
    </>
  );
}
