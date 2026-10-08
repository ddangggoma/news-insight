"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";
import { clientHeaders, requireAdmin, sessionToken } from "@/lib/session";
import type { ChangeResult, TaxOp } from "@/lib/taxonomy-ops";

export type ChangeResponse = { ok: true; result: ChangeResult } | { ok: false; error: string };

async function adminHeaders(): Promise<Record<string, string>> {
  await requireAdmin();
  return { ...(await clientHeaders()), "X-Session-Token": await sessionToken() };
}

function failure(error: unknown): ChangeResponse {
  if (error instanceof ApiError) {
    try {
      const detail = (JSON.parse(error.message) as { detail?: unknown }).detail;
      if (typeof detail === "string") return { ok: false, error: detail };
      if (Array.isArray(detail)) return { ok: false, error: detail.map((d) => (d as { msg?: string }).msg ?? "").join("; ") };
    } catch {
      // not JSON
    }
  }
  return { ok: false, error: "요청에 실패했습니다." };
}

async function post(path: string, body: unknown): Promise<ChangeResponse> {
  try {
    return { ok: true, result: await api.post<ChangeResult>(path, body, await adminHeaders()) };
  } catch (error) {
    return failure(error);
  }
}

export async function previewChanges(ops: TaxOp[]): Promise<ChangeResponse> {
  return post("/api/admin/taxonomy/preview", { ops });
}

export async function applyChanges(ops: TaxOp[], note: string): Promise<ChangeResponse> {
  const response = await post("/api/admin/taxonomy/apply", { ops, note: note || null });
  if (response.ok) revalidatePath("/console", "layout");
  return response;
}

export async function rollbackRevision(id: number): Promise<ChangeResponse> {
  const response = await post(`/api/admin/taxonomy/revisions/${id}/rollback`, {});
  if (response.ok) revalidatePath("/console", "layout");
  return response;
}

export async function nodeCards(nodeId: number): Promise<{ item_id: number; title: string; first_seen_at: string; source: string; node: string }[]> {
  await requireAdmin();
  return api.get(`/api/admin/taxonomy/nodes/${nodeId}/cards`, { limit: 8 });
}
