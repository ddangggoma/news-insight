import { cleanQuery, forwardedIp, recordAccess } from "@/lib/access-log";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

const HREF_MAX = 1_000;

/**
 * The browser reports each page it shows (components/page-view-beacon.tsx) for the access log:
 * only the browser knows a page was opened rather than prefetched. proxy.ts has checked the
 * session; a report from another site or of an off-site address is ignored.
 */
export async function POST(request: Request): Promise<Response> {
  const user = await currentUser();
  if (!user || user.must_change_password) return new Response(null, { status: 401 });
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin") return new Response(null, { status: 403 });
  let href: unknown;
  try {
    href = (JSON.parse(await request.text()) as { href?: unknown }).href;
  } catch {
    return new Response(null, { status: 400 });
  }
  if (typeof href !== "string" || !href.startsWith("/") || href.startsWith("//") || href.length > HREF_MAX) {
    return new Response(null, { status: 400 });
  }
  const target = new URL(href, "http://page.invalid");
  recordAccess({
    user_id: user.id,
    kind: "page",
    method: "GET",
    path: target.pathname,
    query: cleanQuery(target.searchParams),
    ip: forwardedIp(request.headers),
  });
  return new Response(null, { status: 204 });
}
