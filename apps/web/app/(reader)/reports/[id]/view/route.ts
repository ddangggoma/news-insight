import { currentUser, sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";

// The report is stored HTML with model-written text: no scripts run (CSP and the frame sandbox),
// and links leave in a new tab.
const CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'";

/** The written report as a page of its own, for the frame on /reports/{id} and "새 창으로". */
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const user = await currentUser();
  if (!user || user.must_change_password) return new Response("login required", { status: 401 });
  const id = (await params).id;
  const key = process.env.PUBLIC_API_KEY;
  if (!/^\d{1,9}$/.test(id)) return new Response("not found", { status: 404 });
  if (!key) return new Response("reports unavailable", { status: 503 });
  const response = await fetch(`${BASE_URL}/api/public/reports/${id}/html`, {
    headers: { "X-Public-Key": key, "X-Session-Token": await sessionToken() },
    cache: "no-store",
  });
  if (!response.ok) {
    const status = response.status === 404 || response.status === 409 ? response.status : 502;
    return new Response(status === 409 ? "보고서를 아직 쓰는 중입니다." : status === 404 ? "not found" : "report unavailable", {
      status,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new Response(response.body, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": CSP,
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "private, no-store",
    },
  });
}
