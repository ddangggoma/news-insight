"use server";

import { revalidatePath } from "next/cache";

import { ApiError, api } from "@/lib/api";
import type { Role } from "@/lib/auth";
import { clientHeaders, requireAdmin, sessionToken } from "@/lib/session";

export type UserAction = "approve" | "reject" | "suspend" | "reactivate" | "unlock";

export interface ActionResult {
  ok: boolean;
  error?: string;
  temporaryPassword?: string;
}

// The API names the reason for a refusal (last admin, own account, wrong state) in its detail.
function failure(error: unknown): ActionResult {
  if (error instanceof ApiError) {
    try {
      const detail = (JSON.parse(error.message) as { detail?: unknown }).detail;
      if (typeof detail === "string") return { ok: false, error: detail };
    } catch {
      // not JSON: fall through to the generic message
    }
  }
  return { ok: false, error: "요청에 실패했습니다." };
}

async function adminHeaders(): Promise<Record<string, string>> {
  await requireAdmin();
  return { ...(await clientHeaders()), "X-Session-Token": await sessionToken() };
}

async function run(path: string, body?: unknown): Promise<ActionResult> {
  const headers = await adminHeaders();
  try {
    const result = await api.post<{ temporary_password?: string }>(path, body, headers);
    revalidatePath("/console", "layout");
    return { ok: true, temporaryPassword: result?.temporary_password };
  } catch (error) {
    return failure(error);
  }
}

export async function actOnUser(id: number, action: UserAction): Promise<ActionResult> {
  return run(`/api/admin/users/${id}/${action}`);
}

export async function setUserRole(id: number, role: Role): Promise<ActionResult> {
  return run(`/api/admin/users/${id}/role`, { role });
}

export async function resetUserPassword(id: number): Promise<ActionResult> {
  return run(`/api/admin/users/${id}/reset-password`);
}
