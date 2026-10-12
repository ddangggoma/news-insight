"use client";

import NextLink, { useLinkStatus } from "next/link";
import { type ComponentProps, useState } from "react";

import { isRepeat, routeOf, startNavigation } from "@/lib/navigation-state";

type AppLinkProps = Omit<ComponentProps<typeof NextLink>, "href"> & { href: string };

/** Marks the link while its page loads, so CSS can show it (`a:has(> [data-link-pending])`). */
function PendingMark() {
  const { pending } = useLinkStatus();
  return pending ? <span hidden data-link-pending="" /> : null;
}

/**
 * The app's Link (2026-10-12). Next.js prefetches every link that scrolls into view; a list of
 * 30 cards sent well over a hundred requests per page load, and Caddy's rate limit then refused
 * the page itself (HTTP 429). Here a link prefetches only when the pointer or focus reaches it,
 * and a second click on the same link is ignored while its page loads or just after it opened.
 */
export function AppLink({ href, prefetch = false, onNavigate, onMouseEnter, onFocus, onTouchStart, children, ...rest }: AppLinkProps) {
  // armed by the first hover, focus or touch: the link then prefetches the way Next.js would
  const [armed, setArmed] = useState(false);
  const warm = () => {
    if (!armed) setArmed(true);
  };

  return (
    <NextLink
      href={href}
      prefetch={prefetch === false && armed ? null : prefetch}
      onMouseEnter={(event) => {
        warm();
        onMouseEnter?.(event);
      }}
      onFocus={(event) => {
        warm();
        onFocus?.(event);
      }}
      onTouchStart={(event) => {
        warm();
        onTouchStart?.(event);
      }}
      onNavigate={(event) => {
        const here = window.location.pathname + window.location.search;
        const target = routeOf(href, window.location.href);
        if (isRepeat(target)) {
          event.preventDefault(); // loading or just opened: no second request for the same page
          return;
        }
        startNavigation(target, { loading: target !== here });
        onNavigate?.(event);
      }}
      {...rest}
    >
      {children}
      <PendingMark />
    </NextLink>
  );
}
