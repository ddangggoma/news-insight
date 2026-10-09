"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { teamApi } from "@/lib/dossier-api";
import type { CollectionDetail, CommentKind, ItemTeam, TeamComment } from "@/lib/team-types";
import { requireUser } from "@/lib/session";

export async function loadComments(kind: CommentKind, targetId: number): Promise<TeamComment[]> {
  await requireUser();
  return teamApi("GET", `/comments?kind=${kind}&target_id=${targetId}`);
}

export async function addComment(kind: CommentKind, targetId: number, body: string): Promise<TeamComment[]> {
  await requireUser();
  return teamApi("POST", "/comments", { kind, target_id: targetId, body: body.trim().slice(0, 2000) });
}

export async function deleteComment(id: number): Promise<TeamComment[]> {
  await requireUser();
  return teamApi("DELETE", `/comments/${id}`);
}

export async function loadItemTeam(itemId: number): Promise<ItemTeam> {
  await requireUser();
  return teamApi("GET", `/items/${itemId}`);
}

export async function collect(collectionId: number, itemId: number, note?: string): Promise<CollectionDetail> {
  await requireUser();
  const detail = await teamApi<CollectionDetail>("POST", `/collections/${collectionId}/items`, { item_id: itemId, note: note?.slice(0, 500) || null });
  revalidatePath(`/collections/${collectionId}`);
  return detail;
}

export async function uncollect(collectionId: number, itemId: number): Promise<CollectionDetail> {
  await requireUser();
  const detail = await teamApi<CollectionDetail>("DELETE", `/collections/${collectionId}/items/${itemId}`);
  revalidatePath(`/collections/${collectionId}`);
  return detail;
}

export async function newCollection(title: string, itemId?: number): Promise<CollectionDetail> {
  await requireUser();
  const created = await teamApi<CollectionDetail>("POST", "/collections", { title: title.trim().slice(0, 120) });
  revalidatePath("/collections");
  return itemId ? collect(created.id, itemId) : created;
}

export async function createCollection(form: FormData): Promise<void> {
  await requireUser();
  const title = String(form.get("title") ?? "").trim();
  if (title.length < 2) redirect("/collections?error=title");
  const created = await teamApi<CollectionDetail>("POST", "/collections", { title, description: String(form.get("description") ?? "").trim() || null });
  revalidatePath("/collections");
  redirect(`/collections/${created.id}`);
}

export async function archiveCollection(id: number): Promise<void> {
  await requireUser();
  await teamApi("DELETE", `/collections/${id}`);
  revalidatePath("/collections");
  redirect("/collections");
}
