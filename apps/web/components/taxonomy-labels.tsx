"use client";

import { applyTaxonomy, type TaxonomySchemes } from "@/lib/taxonomy-live";

/** Applies the server's schemes in the browser before the rest of the tree renders. */
export function TaxonomyLabels({ taxonomy }: { taxonomy: TaxonomySchemes | null }) {
  applyTaxonomy(taxonomy);
  return null;
}
