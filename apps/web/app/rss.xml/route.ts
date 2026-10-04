import { publicApi } from "@/lib/api";

export const dynamic = "force-dynamic";
const FILTERS = ["field", "theme", "business", "impact"] as const;

/** RSS for the daily briefings, or for one topic (?field= / ?theme= / ?business= / ?impact=). */
export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const params = Object.fromEntries(FILTERS.map((name) => [name, url.searchParams.get(name)?.slice(0, 100)]));
  const upstream = await publicApi.raw("/api/public/feed.xml", params);
  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=300",
    },
  });
}
