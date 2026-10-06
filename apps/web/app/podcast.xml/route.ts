import type { AudioEntry } from "@/lib/briefing-types";
import { podcastFeed, requestOrigin } from "@/lib/rss";
import { REVALIDATE, readerGet } from "@/lib/reader-api";

export async function GET(request: Request): Promise<Response> {
  const entries = await readerGet<AudioEntry[]>("/audio", {}, REVALIDATE.digest);
  return new Response(podcastFeed(requestOrigin(request), entries.slice(0, 30)), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
