import { NextResponse, type NextRequest } from "next/server";

import { ApiError } from "@/lib/api";
import { isRadarKind } from "@/lib/radar";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { CompanyRadar } from "@/lib/reader-types";

const PASSED = ["scope", "signal", "field"] as const;

/** The company radar (plan 12), fetched in the browser when its section nears the viewport. */
export async function GET(request: NextRequest, { params }: { params: Promise<{ period: string; key: string }> }) {
  const { period, key } = await params;
  if (!isRadarKind(period)) return NextResponse.json({ detail: "unknown period" }, { status: 404 });
  const search = request.nextUrl.searchParams;
  const query: Record<string, string | string[]> = { period, key };
  for (const name of PASSED) {
    const values = search.getAll(name);
    if (values.length) query[name] = values.length === 1 ? values[0] : values;
  }
  try {
    return NextResponse.json(await readerGet<CompanyRadar>("/radar/companies", query, REVALIDATE.radarOpen));
  } catch (error) {
    const status = error instanceof ApiError && error.status === 422 ? 422 : 502;
    return NextResponse.json({ detail: "companies unavailable" }, { status });
  }
}
