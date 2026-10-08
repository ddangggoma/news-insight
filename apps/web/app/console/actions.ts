"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import { requireAdmin } from "@/lib/session";
import type { Verdict } from "@/lib/types";

const sourcePath = (key: string) => `/api/admin/sources/${encodeURIComponent(key)}`;

export async function pauseSource(key: string, reason: string): Promise<void> {
  await requireAdmin();
  await api.post(`${sourcePath(key)}/pause`, { reason });
  revalidatePath("/console/sources", "layout");
}

export async function resumeSource(key: string): Promise<void> {
  await requireAdmin();
  await api.post(`${sourcePath(key)}/resume`);
  revalidatePath("/console/sources", "layout");
}

export async function collectNow(key: string): Promise<void> {
  await requireAdmin();
  await api.post(`${sourcePath(key)}/collect`);
  revalidatePath(`/console/sources/${key}`);
}

export async function retryDeadLetter(id: number): Promise<void> {
  await requireAdmin();
  await api.post(`/api/admin/dead-letters/${id}/retry`);
  revalidatePath("/console/dlq");
}

export async function dismissDeadLetter(id: number): Promise<void> {
  await requireAdmin();
  await api.post(`/api/admin/dead-letters/${id}/dismiss`);
  revalidatePath("/console/dlq");
}

export async function submitReview(itemId: number, verdict: Verdict, note: string, seed: string): Promise<void> {
  await requireAdmin();
  await api.post("/api/admin/reviews", { item_id: itemId, verdict, note: note || null, seed });
  revalidatePath("/console/review");
}

export interface TechnologyDraft {
  label: string;
  key?: string;
  theme_key?: string | null;
  kind?: string;
  status?: string;
  aliases?: string[];
}

export async function createTechnology(draft: TechnologyDraft): Promise<{ ok: boolean; error?: string }> {
  await requireAdmin();
  try {
    await api.post("/api/admin/technologies", draft);
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
  revalidatePath("/console/technologies");
  return { ok: true };
}

export async function updateTechnology(
  key: string,
  patch: Partial<TechnologyDraft> & { add_aliases?: string[]; remove_aliases?: string[] },
): Promise<{ ok: boolean; error?: string }> {
  await requireAdmin();
  try {
    await api.patch(`/api/admin/technologies/${encodeURIComponent(key)}`, patch);
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
  revalidatePath("/console/technologies");
  return { ok: true };
}

export async function addWatch(kind: string, value: string): Promise<{ ok: boolean; error?: string }> {
  await requireAdmin();
  try {
    await api.post("/api/admin/watchlist", { kind, value });
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
  revalidatePath("/console/watchlist");
  return { ok: true };
}

export async function removeWatch(id: number): Promise<{ ok: boolean; error?: string }> {
  await requireAdmin();
  try {
    await api.delete(`/api/admin/watchlist/${id}`);
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
  revalidatePath("/console/watchlist");
  return { ok: true };
}

export type BulkAction = "pause" | "resume" | "retire";

export async function bulkSources(
  keys: string[],
  action: BulkAction,
  reason: string,
): Promise<{ ok: boolean; done: string[]; failed: { key: string; error: string }[]; error?: string }> {
  await requireAdmin();
  try {
    const result = await api.post<{ done: string[]; failed: { key: string; error: string }[] }>("/api/admin/sources/bulk", { keys, action, reason });
    revalidatePath("/console/sources", "layout");
    return { ok: true, ...result };
  } catch (error) {
    return { ok: false, done: [], failed: [], error: error instanceof Error ? error.message : String(error) };
  }
}
