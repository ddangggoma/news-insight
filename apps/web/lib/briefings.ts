import "server-only";

import { ApiError } from "@/lib/api";
import type { BriefingEntry, PublicBriefing } from "@/lib/briefing-types";
import { REVALIDATE, readerGet } from "@/lib/reader-api";
import type { Page } from "@/lib/types";

async function orNull<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export const briefings = {
  latest: () => orNull(readerGet<PublicBriefing>("/briefings/latest", {}, REVALIDATE.digest)),
  on: (day: string) => orNull(readerGet<PublicBriefing>(`/briefings/${encodeURIComponent(day)}`, {}, REVALIDATE.digest)),
  recent: async () => (await readerGet<Page<BriefingEntry>>("/briefings", { size: 14 }, REVALIDATE.digest)).items,
};
