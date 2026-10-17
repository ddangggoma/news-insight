import { cleanQuery, forwardedIp, recordAccess } from "@/lib/access-log";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Caddy's forward_auth asks here before serving a spoken briefing from /media (plan 14):
 * Caddy serves those files itself, so without this they would bypass the login. Caddy hides
 * /internal from the outside; it calls this over the compose network with the visitor's cookie,
 * the file in X-Forwarded-Uri and the visitor's address in X-Forwarded-For.
 */
export async function GET(request: Request): Promise<Response> {
  const user = await currentUser();
  const allowed = user !== null && !user.must_change_password;
  const uri = request.headers.get("x-forwarded-uri");
  if (allowed && uri) {
    const target = new URL(uri, "http://media.invalid");
    recordAccess({
      user_id: user.id,
      kind: "media",
      method: request.headers.get("x-forwarded-method") ?? "GET",
      path: target.pathname,
      query: cleanQuery(target.searchParams),
      ip: forwardedIp(request.headers),
    });
  }
  return new Response(null, { status: allowed ? 204 : 401 });
}
