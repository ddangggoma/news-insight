"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

import { finishNavigation, pendingRoute, subscribe } from "@/lib/navigation-state";

/** A thin bar at the top while a page is loading; it ends when the URL changes. */
export function NavigationProgress() {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const pending = useSyncExternalStore(subscribe, pendingRoute, () => null);

  useEffect(() => {
    finishNavigation();
  }, [pathname, search]);

  return (
    <div
      role="progressbar"
      aria-label="페이지를 불러오는 중"
      aria-hidden={pending === null}
      data-active={pending !== null}
      className="navigation-progress"
    />
  );
}
