import "server-only";

import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { applyTaxonomy, type TaxonomySchemes } from "@/lib/taxonomy-live";

/** The current schemes (cached like other reader data), applied to the label records. */
export async function loadTaxonomy(): Promise<TaxonomySchemes | null> {
  try {
    const taxonomy = await readerGet<TaxonomySchemes>("/taxonomy/schemes", {}, REVALIDATE.taxonomy);
    applyTaxonomy(taxonomy);
    return taxonomy;
  } catch {
    return null; // the generated labels stand in until the API answers
  }
}
