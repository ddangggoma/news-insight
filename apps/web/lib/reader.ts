import "server-only";

import { publicApi } from "@/lib/api";
import type { QueryValue } from "@/lib/query";
import type { ArchiveEntry, ReaderBriefing, ReaderCard, ReaderPage, TaxonomyCounts } from "@/lib/reader-types";

export const EMPTY_COUNTS: TaxonomyCounts = { window_days: 30, total: 0, fields: {}, themes: {}, businesses: {}, impacts: {} };

export const reader = {
  latest: () => publicApi.get<ReaderBriefing | null>("/api/public/briefings/latest").then((b) => b ?? null),
  briefing: (day: string) => publicApi.get<ReaderBriefing>(`/api/public/briefings/${encodeURIComponent(day)}`),
  archive: (page: number) => publicApi.get<ReaderPage<ArchiveEntry>>("/api/public/archive", { page, size: 30 }),
  cards: (params: Record<string, QueryValue>) => publicApi.get<ReaderPage<ReaderCard>>("/api/public/cards", params),
  taxonomy: async () => (await publicApi.get<TaxonomyCounts>("/api/public/taxonomy").catch(() => null)) ?? EMPTY_COUNTS,
};
