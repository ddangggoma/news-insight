import type { Metadata } from "next";

import { renderDomainPage } from "@/lib/domain-page";
import type { SearchParams } from "@/lib/params";

export const metadata: Metadata = { title: "연구", robots: { index: false } };

export default async function ResearchPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return renderDomainPage("research", searchParams);
}
