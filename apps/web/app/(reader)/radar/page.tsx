import { redirect } from "next/navigation";

import { radarHref } from "@/components/reader/radar";
import { param, type SearchParams } from "@/lib/params";
import { isRadarKind } from "@/lib/radar";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { SCOPES, type Scope } from "@/lib/reader-filters";
import type { Radar } from "@/lib/reader-types";

/** /radar?period=month → the current month's radar. */
export default async function RadarIndex({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const requested = param(sp, "period") ?? "week";
  const period = isRadarKind(requested) ? requested : "week";
  const scopeParam = param(sp, "scope");
  const scope: Scope = scopeParam && scopeParam in SCOPES ? (scopeParam as Scope) : "relevant";
  const radar = await readerGet<Radar>("/radar", { period, scope }, REVALIDATE.radarOpen);
  redirect(radarHref(radar.window.kind, radar.window.key, { scope }));
}
