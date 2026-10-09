import type { Metadata } from "next";

import { DossierForm } from "@/components/reader/dossier-form";
import { scopeOptions } from "@/lib/scope-options";
import { requireUser } from "@/lib/session";
import { loadTaxonomy } from "@/lib/taxonomy-server";

export const metadata: Metadata = { title: "새 주제 파일", robots: { index: false } };

export default async function NewDossierPage() {
  await requireUser();
  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6 md:px-6">
      <h1 className="text-xl font-semibold">새 주제 파일</h1>
      <DossierForm scopes={scopeOptions(await loadTaxonomy(), 3)} />
    </main>
  );
}
