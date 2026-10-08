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

export interface SimilarCard {
  item_id: number;
  title: string | null;
  similarity: number;
  first_seen_at: string;
  labelled: boolean;
}

/** Cards that read like the text, plan 15-6 (needs the embedding model on the host). */
export async function similarCards(text: string, nodeId: number | null): Promise<{ ok: true; cards: SimilarCard[]; unlabelled: number } | { ok: false; error: string }> {
  await requireAdmin();
  try {
    const result = await api.post<{ cards: SimilarCard[]; unlabelled: number }>("/api/admin/taxonomy/similar", { text, node_id: nodeId, limit: 20 });
    return { ok: true, ...result };
  } catch {
    return { ok: false, error: "임베딩 모델(LM Studio bge-m3)에 연결할 수 없습니다." };
  }
}

export async function nodeMisfits(nodeId: number): Promise<{ members: number; mean_similarity: number | null; cards: { item_id: number; title: string | null; similarity: number }[] }> {
  await requireAdmin();
  return api.get(`/api/admin/taxonomy/nodes/${nodeId}/misfits`, { limit: 10 });
}

export async function candidateClusters(): Promise<{ ok: true; clusters: { label: string; count: number; phrases: { key: string; label: string; count: number }[] }[] } | { ok: false; error: string }> {
  await requireAdmin();
  try {
    return { ok: true, clusters: await api.get("/api/admin/taxonomy/candidates/clusters", { days: 30 }) };
  } catch {
    return { ok: false, error: "임베딩 모델(LM Studio bge-m3)에 연결할 수 없습니다." };
  }
}
