import type { Metadata } from "next";

import { DEAL_DAYS, DealsView } from "@/components/reader/deals-view";
import { DEAL_KIND_LABEL, type DealKind, type DealView } from "@/lib/deal-types";
import { param, type SearchParams } from "@/lib/params";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "투자·제휴", robots: { index: false } };

export default async function DealsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireUser();
  const sp = await searchParams;
  const days = DEAL_DAYS.includes(Number(param(sp, "days"))) ? Number(param(sp, "days")) : 90;
  const kindParam = param(sp, "kind");
  const kind = kindParam && kindParam in DEAL_KIND_LABEL ? (kindParam as DealKind) : undefined;
  const company = param(sp, "company") ?? undefined;
  const view = await readerGet<DealView>("/deals", { days, kind, company }, REVALIDATE.feed);
  return <DealsView view={view} days={days} kind={kind} company={company} />;
}
