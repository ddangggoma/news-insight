import { timingSafeEqual } from "node:crypto";

import { revalidateTag } from "next/cache";

export const dynamic = "force-dynamic";

function sameKey(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

/** Drop cached reader responses after a deploy (scripts/release.sh). Caddy hides /internal. */
export async function POST(request: Request): Promise<Response> {
  if (!sameKey(request.headers.get("x-console-key"), process.env.CONSOLE_API_KEY)) {
    return new Response("forbidden", { status: 403 });
  }
  revalidateTag("reader", { expire: 0 });
  return Response.json({ revalidated: ["reader"] });
}
