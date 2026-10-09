import { type NextRequest } from "next/server";

import { currentUser, sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";
const FORMATS = new Set(["md", "docx", "pptx"]);

/** /export/briefing/{date} · /export/periodic/{week|month}/{key} · /export/dossier/{id}, ?format= */
function apiPath(path: string[]): string | null {
  const [kind, ...rest] = path;
  if (kind === "briefing" && rest.length === 1 && /^\d{4}-\d{2}-\d{2}$/.test(rest[0])) return `/api/public/export/briefing/${rest[0]}`;
  if (kind === "periodic" && rest.length === 2 && ["week", "month"].includes(rest[0]) && /^[\dA-Z-]{4,10}$/.test(rest[1])) {
    return `/api/public/export/periodic/${rest[0]}/${rest[1]}`;
  }
  if (kind === "dossier" && rest.length === 1 && /^\d{1,9}$/.test(rest[0])) return `/api/public/dossiers/${rest[0]}/export`;
  return null;
}

/** Report files (plan 16 #11), streamed from the API for a signed-in reader. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const user = await currentUser();
  if (!user || user.must_change_password) return new Response("login required", { status: 401 });
  const target = apiPath((await params).path);
  const format = request.nextUrl.searchParams.get("format") ?? "md";
  const key = process.env.PUBLIC_API_KEY;
  if (!target || !FORMATS.has(format)) return new Response("not found", { status: 404 });
  if (!key) return new Response("export unavailable", { status: 503 });
  const response = await fetch(`${BASE_URL}${target}?format=${format}`, {
    headers: { "X-Public-Key": key, "X-Session-Token": await sessionToken() },
    cache: "no-store",
  });
  if (!response.ok) return new Response(response.status === 404 ? "not found" : "export failed", { status: response.status === 404 ? 404 : 502 });
  return new Response(response.body, {
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition": response.headers.get("content-disposition") ?? "attachment",
      "Cache-Control": "private, no-store",
    },
  });
}
