"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api";
import { apiDetail, reportApi } from "@/lib/dossier-api";
import type { ReportDetail } from "@/lib/report-types";
import { requireUser } from "@/lib/session";

export interface RequestState {
  error?: string;
}

export async function requestReport(_: RequestState, form: FormData): Promise<RequestState> {
  await requireUser();
  const dossier = Number(form.get("dossier_id") ?? 0);
  const body = {
    topic: String(form.get("topic") ?? "").trim(),
    brief: String(form.get("brief") ?? "").trim() || null,
    days: Number(form.get("days") ?? 90),
    dossier_id: dossier > 0 ? dossier : null,
  };
  if (body.topic.length < 2) return { error: "주제를 두 글자 이상 입력하세요." };
  let created: ReportDetail;
  try {
    created = await reportApi<ReportDetail>("POST", "", body);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 422 || error.status === 429)) return { error: apiDetail(error) };
    throw error;
  }
  revalidatePath("/reports");
  redirect(`/reports/${created.id}`);
}

export async function retryReport(id: number): Promise<void> {
  await requireUser();
  await reportApi("POST", `/${id}/retry`);
  revalidatePath(`/reports/${id}`);
}

export async function archiveReport(id: number): Promise<void> {
  await requireUser();
  await reportApi("DELETE", `/${id}`);
  revalidatePath("/reports");
  redirect("/reports");
}
