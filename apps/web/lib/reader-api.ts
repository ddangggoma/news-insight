import "server-only";

import { ApiError } from "@/lib/api";
import { type QueryValue, withQuery } from "@/lib/query";

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";

/** Seconds a reader response may be served from the Next.js data cache. */
export const REVALIDATE = { feed: 300, digest: 600, radarOpen: 600, radarClosed: 86400, taxonomy: 3600 } as const;

/**
 * Reader API client. Uses PUBLIC_API_KEY, never the console key, and lets Next.js cache
 * responses so public traffic does not reach the API for every page view.
 */
/** Public API shape hash; part of every cached URL so a deploy never mixes old JSON in. */
async function schemaVersion(key: string): Promise<string | undefined> {
  try {
    const response = await fetch(`${BASE_URL}/api/public/version`, {
      headers: { "X-Public-Key": key },
      next: { revalidate: 30, tags: ["reader"] },
    });
    return response.ok ? ((await response.json()) as { schema: string }).schema : undefined;
  } catch {
    return undefined;
  }
}

export async function readerGet<T>(
  path: string,
  params: Record<string, QueryValue> = {},
  revalidate: number = REVALIDATE.feed,
): Promise<T> {
  const key = process.env.PUBLIC_API_KEY;
  if (!key) throw new ApiError(503, "PUBLIC_API_KEY is not configured for the web server");
  const version = await schemaVersion(key);
  const response = await fetch(`${BASE_URL}/api/public${withQuery(path, { ...params, _v: version })}`, {
    headers: { "X-Public-Key": key },
    next: { revalidate, tags: ["reader"] },
  });
  if (!response.ok) {
    throw new ApiError(response.status, (await response.text()) || response.statusText);
  }
  return (await response.json()) as T;
}

/** Reader POST without caching (questions to the local model, plan 16 #1). */
export async function readerPost<T>(path: string, body: unknown): Promise<T> {
  const key = process.env.PUBLIC_API_KEY;
  if (!key) throw new ApiError(503, "PUBLIC_API_KEY is not configured for the web server");
  const response = await fetch(`${BASE_URL}/api/public${path}`, {
    method: "POST",
    headers: { "X-Public-Key": key, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, (await response.text()) || response.statusText);
  }
  return (await response.json()) as T;
}
