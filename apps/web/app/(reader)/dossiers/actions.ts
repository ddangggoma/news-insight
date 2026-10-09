"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api";
import { apiDetail, dossierApi } from "@/lib/dossier-api";
import { type DossierDetail, type Hypothesis, type HypothesisStatus, type Stance, type Suggestion, splitList } from "@/lib/dossier-types";
import { requireUser } from "@/lib/session";

export interface FormState {
  error?: string;
}

export async function saveDossier(_: FormState, form: FormData): Promise<FormState> {
  await requireUser();
  const id = Number(form.get("id") ?? 0);
  const body = {
    title: String(form.get("title") ?? "").trim(),
    description: String(form.get("description") ?? "").trim() || null,
    statement: String(form.get("statement") ?? "").trim() || null,
    min_similarity: Number(form.get("min_similarity") ?? 0.6),
    keywords: splitList(String(form.get("keywords") ?? "")),
    exclude: splitList(String(form.get("exclude") ?? "")),
    companies: splitList(String(form.get("companies") ?? "")),
    nodes: form.getAll("nodes").map(String),
  };
  if (body.title.length < 2) return { error: "제목을 두 글자 이상 입력하세요." };
  let saved: DossierDetail;
  try {
    saved = id ? await dossierApi("PUT", `/${id}`, body) : await dossierApi("POST", "", body);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) return { error: apiDetail(error) };
    throw error;
  }
  revalidatePath("/dossiers");
  redirect(`/dossiers/${saved.id}`);
}

export async function archiveDossier(id: number): Promise<void> {
  await requireUser();
  await dossierApi("DELETE", `/${id}`);
  revalidatePath("/dossiers");
  redirect("/dossiers");
}

export async function addHypothesis(id: number, text: string): Promise<Hypothesis[]> {
  await requireUser();
  return dossierApi("POST", `/${id}/hypotheses`, { text: text.trim().slice(0, 500) });
}

export async function updateHypothesis(id: number, hypothesisId: number, patch: { text?: string; status?: HypothesisStatus }): Promise<Hypothesis[]> {
  await requireUser();
  return dossierApi("PATCH", `/${id}/hypotheses/${hypothesisId}`, patch);
}

export async function deleteHypothesis(id: number, hypothesisId: number): Promise<Hypothesis[]> {
  await requireUser();
  return dossierApi("DELETE", `/${id}/hypotheses/${hypothesisId}`);
}

export async function suggestEvidence(id: number, hypothesisId: number): Promise<Suggestion[]> {
  await requireUser();
  return dossierApi("GET", `/${id}/hypotheses/${hypothesisId}/suggestions`);
}

export async function addEvidence(id: number, hypothesisId: number, itemId: number, stance: Stance, note?: string): Promise<Hypothesis[]> {
  await requireUser();
  return dossierApi("POST", `/${id}/hypotheses/${hypothesisId}/evidence`, { item_id: itemId, stance, note: note?.slice(0, 500) || null });
}

export async function deleteEvidence(id: number, evidenceId: number): Promise<Hypothesis[]> {
  await requireUser();
  return dossierApi("DELETE", `/${id}/evidence/${evidenceId}`);
}
