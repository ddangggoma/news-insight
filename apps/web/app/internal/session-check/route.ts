import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Caddy's forward_auth asks here before serving a spoken briefing from /media (plan 14):
 * Caddy serves those files itself, so without this they would bypass the login. Caddy hides
 * /internal from the outside; it calls this over the compose network with the visitor's cookie.
 */
export async function GET(): Promise<Response> {
  const user = await currentUser();
  return new Response(null, { status: user && !user.must_change_password ? 204 : 401 });
}
