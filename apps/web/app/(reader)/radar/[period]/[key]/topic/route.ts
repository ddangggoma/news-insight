import { NextResponse, type NextRequest } from "next/server";

import { ApiError } from "@/lib/api";
import { isRadarKind } from "@/lib/radar";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import { currentUser } from "@/lib/session";
import type { TopicDetail } from "@/lib/reader-types";

const PASSED = ["scope", "signal", "field", "kind", "value"] as const;

/** One topic's detail for the radar's side panel, fetched in the browser when the focus changes (WEB-1). */
export async function GET(request: NextRequest, { params }: { params: Promise<{ period: string; key: string }> }) {
  if (!(await currentUser())) return NextResponse.json({ detail: "login required" }, { status: 401 });
  const { period, key } = await params;
  if (!isRadarKind(period)) return NextResponse.json({ detail: "unknown period" }, { status: 404 });
  const search = request.nextUrl.searchParams;
  const query: Record<string, string | string[]> = { period, key };
  for (const name of PASSED) {
    const values = search.getAll(name);
    if (values.length) query[name] = values.length === 1 ? values[0] : values;
  }
  try {
    return NextResponse.json(await readerGet<TopicDetail>("/radar/topic", query, REVALIDATE.radarOpen));
  } catch (error) {
    const status = error instanceof ApiError && error.status === 422 ? 422 : 502;
    return NextResponse.json({ detail: "topic unavailable" }, { status });
  }
}
