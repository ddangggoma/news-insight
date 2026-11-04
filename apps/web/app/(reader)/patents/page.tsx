import type { Metadata } from "next";

import { renderDomainPage } from "@/lib/domain-page";
import type { SearchParams } from "@/lib/params";

export const metadata: Metadata = { title: "특허", robots: { index: false } };

export default async function PatentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return renderDomainPage("patent", searchParams);
}
