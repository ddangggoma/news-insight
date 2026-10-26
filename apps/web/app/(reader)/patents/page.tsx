import type { Metadata } from "next";

import { PatentsView } from "@/components/reader/patents-view";
import { param, pageParam, type SearchParams } from "@/lib/params";
import type { PatentView } from "@/lib/patent-types";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "특허 신호", robots: { index: false } };

export default async function PatentsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const kind = param(sp, "kind") === "quarter" ? "quarter" : "month";
  const page = pageParam(sp);
  const view = await readerGet<PatentView>("/patents", { kind, page }, REVALIDATE.feed);
  return <PatentsView view={view} kind={kind} page={page} />;
}
