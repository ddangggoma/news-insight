import { digestFeed, requestOrigin } from "@/lib/rss";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { DigestSummary, Page } from "@/lib/types";

export async function GET(request: Request): Promise<Response> {
  const digests = await readerGet<Page<DigestSummary>>("/digests", { size: 20 }, REVALIDATE.digest);
  return new Response(digestFeed(requestOrigin(request), digests.items), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
