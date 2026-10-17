// Shared by proxy.ts, the page-view route and the media session check, so no "server-only" here: nothing in this file runs in the browser.

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";

// Access log (console → 접속 기록). Requests are noted here and one call every FLUSH_MS sends the
// batch, so a page load costs no API call. A batch that cannot be sent is dropped, never retried:
// the log is a record, not a ledger.
//
// Where each kind comes from: Next.js strips the RSC and prefetch headers before proxy.ts runs
// (and hides them from server components too), so the proxy cannot tell a page someone opened
// from a link they only hovered. Pages are therefore reported by the browser (PageViewBeacon →
// /page-view); the proxy notes what it can tell for sure: server actions and route handlers.
const FLUSH_MS = 5_000;
const BATCH_MAX = 500; // the API's limit per call
const BUFFER_MAX = 2_000; // while the API is down, the oldest entries go first
// The same entry again within this long is not a new visit: a double mount, a reload, the range
// requests a player makes while a spoken briefing plays. Actions always count.
const REPEAT_MS: Record<AccessKind, number> = { page: 5_000, api: 30_000, action: 0, media: 30 * 60_000 };
const RECENT_MAX = 5_000;
export const PAGE_VIEW_PATH = "/page-view";

// The route handlers (app/**/route.ts) a browser calls; tests/access-log.test.ts keeps this in
// step with the app directory.
export const ROUTE_HANDLERS: readonly RegExp[] = [
  /^\/export\/.+/,
  /^\/console\/review\/export$/,
  /^\/radar\/[^/]+\/[^/]+\/(topic|companies)$/,
  /^\/reports\/[^/]+\/view$/,
];

export type AccessKind = "page" | "action" | "api" | "media";

export interface AccessEntry {
  at: string;
  user_id: number;
  kind: AccessKind;
  method: string;
  path: string;
  query?: string;
  ip?: string;
}

type State = { entries: AccessEntry[]; timer: ReturnType<typeof setTimeout> | null; recent: Map<string, number> };
// On globalThis like the session cache: one buffer for the whole standalone server.
const state: State = ((globalThis as { __niAccess?: State }).__niAccess ??= { entries: [], timer: null, recent: new Map() });

/** What the proxy notes for this request: a server action, a route handler, or nothing (pages
 * come from the page-view beacon). */
export function accessKind(headers: Headers, pathname: string): AccessKind | null {
  if (headers.has("next-action")) return "action";
  if (ROUTE_HANDLERS.some((pattern) => pattern.test(pathname))) return "api";
  return null;
}

/** The browser's address as Caddy forwarded it (Caddy is the only way in). */
export function forwardedIp(headers: Headers): string | undefined {
  return headers.get("x-forwarded-for")?.split(",")[0]?.trim() || undefined;
}

/** The query without Next.js's cache-busting `_rsc`, or undefined when nothing is left. */
export function cleanQuery(search: URLSearchParams): string | undefined {
  const kept = new URLSearchParams(search);
  kept.delete("_rsc");
  return kept.toString() || undefined;
}

/** Note one request; the batch goes to the API within FLUSH_MS. Never throws. */
export function recordAccess(entry: Omit<AccessEntry, "at">, now: number = Date.now()): void {
  const repeat = REPEAT_MS[entry.kind];
  if (repeat > 0) {
    const key = `${entry.user_id} ${entry.kind} ${entry.method} ${entry.path}?${entry.query ?? ""}`;
    const last = state.recent.get(key);
    if (last !== undefined && now - last < repeat) return;
    if (state.recent.size >= RECENT_MAX) state.recent.clear();
    state.recent.set(key, now);
  }
  state.entries.push({ ...entry, at: new Date(now).toISOString() });
  if (state.entries.length > BUFFER_MAX) state.entries.splice(0, state.entries.length - BUFFER_MAX);
  if (state.timer === null) {
    state.timer = setTimeout(() => void flushAccessLog(), FLUSH_MS);
    state.timer.unref?.();
  }
}

/** Send what is waiting (the timer calls this; tests call it directly). */
export async function flushAccessLog(): Promise<void> {
  if (state.timer !== null) clearTimeout(state.timer);
  state.timer = null;
  const key = process.env.CONSOLE_API_KEY;
  while (state.entries.length > 0) {
    const batch = state.entries.splice(0, BATCH_MAX);
    if (!key) return;
    try {
      const response = await fetch(`${BASE_URL}/api/admin/access-log`, {
        method: "POST",
        headers: { "X-Console-Key": key, "Content-Type": "application/json" },
        body: JSON.stringify({ entries: batch }),
        cache: "no-store",
      });
      if (!response.ok) console.warn(`access log: ${batch.length} entries not stored (${response.status})`);
    } catch (error) {
      console.warn(`access log: ${batch.length} entries not sent (${String(error)})`);
    }
  }
}

/** Forget everything waiting (tests). */
export function clearAccessLog(): void {
  if (state.timer !== null) clearTimeout(state.timer);
  state.timer = null;
  state.entries.length = 0;
  state.recent.clear();
}

/** What is waiting to be sent (tests). */
export function pendingAccess(): readonly AccessEntry[] {
  return state.entries;
}
