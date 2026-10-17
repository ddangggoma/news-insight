"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect } from "react";

const ENDPOINT = "/page-view";
const SIGNED_OUT = new Set(["/login", "/signup"]);

/**
 * Reports each page the browser shows to the access log (console → 접속 기록), on the first load
 * and on every client-side navigation. The server cannot tell these apart from link prefetches:
 * Next.js hides that difference from the proxy. A refresh of the same page reports nothing.
 */
export function PageViewBeacon() {
  const pathname = usePathname();
  const search = useSearchParams().toString();

  useEffect(() => {
    if (SIGNED_OUT.has(pathname)) return;
    const body = JSON.stringify({ href: search ? `${pathname}?${search}` : pathname });
    // sendBeacon queues the report without holding up the page; fetch is the fallback
    if (typeof navigator.sendBeacon === "function" && navigator.sendBeacon(ENDPOINT, body)) return;
    void fetch(ENDPOINT, { method: "POST", body, keepalive: true, credentials: "same-origin" }).catch(() => undefined);
  }, [pathname, search]);

  return null;
}
