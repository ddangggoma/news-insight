// The page navigation in progress, shared by every AppLink and the progress bar (2026-10-12).
// While a click is still loading, clicking the same link again is ignored instead of starting
// another request for the same page; the progress bar tells the reader something is happening.
// A prefetched page opens in under 100 ms, after which more clicks on the same link would each
// reload it: those are ignored too for REPEAT_GUARD_MS.

type Listener = () => void;

/** Give up on a navigation that never reports back (a failed request, a hard reload). */
export const NAVIGATION_TIMEOUT_MS = 20_000;
/** A second click on the same link this soon after the first does nothing. */
export const REPEAT_GUARD_MS = 3_000;

let pending: string | null = null;
let last: { route: string; at: number } | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** pathname + search of an href, resolved against the current page; hashes do not count. */
export function routeOf(href: string, base: string): string {
  const url = new URL(href, base);
  return url.pathname + url.search;
}

export function pendingRoute(): string | null {
  return pending;
}

/** Whether a click on `route` would repeat a navigation that is loading or just happened. */
export function isRepeat(route: string, now: number = Date.now()): boolean {
  return pending === route || (last !== null && last.route === route && now - last.at < REPEAT_GUARD_MS);
}

/** Remember a click; `loading` is false for a link to the page already open (the URL stays). */
export function startNavigation(route: string, { loading = true, now = Date.now() } = {}): void {
  last = { route, at: now };
  if (!loading) return;
  pending = route;
  clearTimeout(timer);
  timer = setTimeout(finishNavigation, NAVIGATION_TIMEOUT_MS);
  emit();
}

/** Forget every click (tests). */
export function resetNavigation(): void {
  last = null;
  finishNavigation();
}

export function finishNavigation(): void {
  if (pending === null) return;
  pending = null;
  clearTimeout(timer);
  emit();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
