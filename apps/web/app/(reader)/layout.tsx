import { type ReactNode, Suspense } from "react";

import { BottomNav } from "@/components/reader/bottom-nav";
import { ReaderHeader } from "@/components/reader/reader-header";
import { TaxonomyLabels } from "@/components/taxonomy-labels";
import { requireUser } from "@/lib/session";
import { loadTaxonomy } from "@/lib/taxonomy-server";

export default async function ReaderLayout({ children, sheet }: { children: ReactNode; sheet: ReactNode }) {
  const [user, taxonomy] = await Promise.all([requireUser(), loadTaxonomy()]);
  return (
    <div className="min-h-screen bg-background">
      <TaxonomyLabels taxonomy={taxonomy} />
      <Suspense>
        <ReaderHeader user={{ name: user.name, admin: user.role === "admin" }} />
      </Suspense>
      <div className="pb-16 md:pb-0">{children}</div>
      {sheet}
      <BottomNav />
    </div>
  );
}
