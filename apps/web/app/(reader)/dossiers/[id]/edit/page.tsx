import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DossierForm } from "@/components/reader/dossier-form";
import { ApiError } from "@/lib/api";
import { dossierApi } from "@/lib/dossier-api";
import type { DossierDetail } from "@/lib/dossier-types";
import { scopeOptions } from "@/lib/scope-options";
import { requireUser } from "@/lib/session";
import { loadTaxonomy } from "@/lib/taxonomy-server";

export const metadata: Metadata = { title: "주제 파일 편집", robots: { index: false } };

export default async function EditDossierPage({ params }: { params: Promise<{ id: string }> }) {
  await requireUser();
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id < 1) notFound();
  const dossier = await dossierApi<DossierDetail>("GET", `/${id}`).catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  });
  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6 md:px-6">
      <h1 className="text-xl font-semibold">주제 파일 편집</h1>
      <DossierForm scopes={scopeOptions(await loadTaxonomy(), 3)} dossier={dossier} />
    </main>
  );
}
