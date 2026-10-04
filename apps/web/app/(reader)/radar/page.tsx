import { redirect } from "next/navigation";

import { param, type SearchParams } from "@/lib/params";
import { isRadarKind, radarHref } from "@/lib/radar";
import { radarView } from "@/lib/radar-view";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { Radar } from "@/lib/reader-types";

/** /radar?period=month → the current month's radar, keeping the filters. */
export default async function RadarIndex({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const requested = param(sp, "period") ?? "week";
  const period = isRadarKind(requested) ? requested : "week";
  const view = radarView(sp);
  const radar = await readerGet<Radar>("/radar", { period, scope: view.scope, business: view.business, field: view.field ?? undefined }, REVALIDATE.radarOpen);
  redirect(radarHref(radar.window.kind, radar.window.key, view));
}
