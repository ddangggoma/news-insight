import "server-only";

import { ApiError } from "@/lib/api";
import { sessionToken } from "@/lib/session";

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";

/** Topic dossier API (plan 16 #4): never cached, and always with the reader's session. */
export async function dossierApi<T>(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  const key = process.env.PUBLIC_API_KEY;
  if (!key) throw new ApiError(503, "PUBLIC_API_KEY is not configured for the web server");
  const response = await fetch(`${BASE_URL}/api/public/dossiers${path}`, {
    method,
    headers: {
      "X-Public-Key": key,
      "X-Session-Token": await sessionToken(),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(response.status, (await response.text()) || response.statusText);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/** The API's 422 detail as a sentence for the form. */
export function apiDetail(error: ApiError): string {
  try {
    const detail = (JSON.parse(error.message) as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? "").join(" ");
  } catch {
    // not JSON
  }
  return "저장하지 못했습니다.";
}
