import type { AudioEntry } from "@/lib/briefing-types";
import { podcastFeed } from "@/lib/rss";
import { REVALIDATE, readerGet } from "@/lib/reader-api";

export async function GET(request: Request): Promise<Response> {
  const entries = await readerGet<AudioEntry[]>("/audio", {}, REVALIDATE.digest);
  return new Response(podcastFeed(new URL(request.url).origin, entries.slice(0, 30)), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
