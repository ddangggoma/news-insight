"use server";

import { revalidatePath } from "next/cache";

import { api } from "@/lib/api";
import type { Verdict } from "@/lib/types";

const sourcePath = (key: string) => `/api/admin/sources/${encodeURIComponent(key)}`;

export async function pauseSource(key: string, reason: string): Promise<void> {
  await api.post(`${sourcePath(key)}/pause`, { reason });
  revalidatePath("/console/sources", "layout");
}

export async function resumeSource(key: string): Promise<void> {
  await api.post(`${sourcePath(key)}/resume`);
  revalidatePath("/console/sources", "layout");
}

export async function collectNow(key: string): Promise<void> {
  await api.post(`${sourcePath(key)}/collect`);
  revalidatePath(`/console/sources/${key}`);
}

export async function retryDeadLetter(id: number): Promise<void> {
  await api.post(`/api/admin/dead-letters/${id}/retry`);
  revalidatePath("/console/dlq");
}

export async function dismissDeadLetter(id: number): Promise<void> {
  await api.post(`/api/admin/dead-letters/${id}/dismiss`);
  revalidatePath("/console/dlq");
}

export async function submitReview(itemId: number, verdict: Verdict, note: string, seed: string): Promise<void> {
  await api.post("/api/admin/reviews", { item_id: itemId, verdict, note: note || null, seed });
  revalidatePath("/console/review");
}
