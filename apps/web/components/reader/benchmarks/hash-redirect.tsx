"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { benchmarkHref, isSiteKey } from "@/lib/benchmark-types";

/**
 * Old links to the leaderboards (`/spotlight?tab=ai#benchmarks`, and `#bench-<site>` cards) from
 * when they sat under AI 모델·서비스. The server never sees a hash, so the AI tab mounts this:
 * it sends such a link on to the 벤치마크 tab (to that site when the hash names one) and renders
 * nothing.
 */
export function BenchmarksHashRedirect({ date }: { date: string | null }) {
  const router = useRouter();
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (hash !== "benchmarks" && !hash.startsWith("bench-")) return;
    const named = /^bench-([a-z0-9_]+)$/.exec(hash)?.[1];
    router.replace(benchmarkHref(named && isSiteKey(named) ? named : null, date));
  }, [router, date]);
  return null;
}
