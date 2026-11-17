"use client";

import { useState } from "react";

import { SpotlightFilterBar } from "@/components/reader/spotlight/filters";
import { NewsOverviewPanel } from "@/components/reader/spotlight/news-overview";
import { Overview } from "@/components/reader/spotlight/overview";
import { SectionList } from "@/components/reader/spotlight/section-list";
import {
  GROUP_KEYS,
  SECTION_KEYS,
  type SectionKey,
  type SpotlightFilters,
  type SpotlightView,
  fieldCounts,
  filterEntries,
  spotlightHref,
} from "@/lib/spotlight-types";

/**
 * The overview or one section's lists with the field and group filters above them. Filtering
 * happens here, on the entries already loaded; the address keeps `?field=` and `?group=` so a
 * reload or a shared link opens the same view (the server renders the initial filters). The
 * news tab opens with 오늘의 구도 (themes and interest areas), which the filters do not narrow.
 */
export function SpotlightBrowser({
  view,
  tab,
  date,
  initial,
}: {
  view: SpotlightView;
  tab: "overview" | SectionKey;
  date: string | null;
  initial: SpotlightFilters;
}) {
  const [filters, setFilters] = useState<SpotlightFilters>(initial);
  const scope = tab === "overview" ? SECTION_KEYS.flatMap((key) => view.sections[key] ?? []) : (view.sections[tab] ?? []);
  // the field chips count within the open group, so each count is what a click would show
  const fields = fieldCounts(filterEntries(scope, { field: null, group: filters.group }));
  const total = filterEntries(scope, { field: null, group: filters.group }).length;
  const groups = filters.group ? [filters.group] : GROUP_KEYS;
  const filtered = filters.field !== null || filters.group !== null;

  const change = (next: SpotlightFilters) => {
    setFilters(next);
    window.history.replaceState(null, "", spotlightHref(tab, date, next));
  };

  const narrowed: SpotlightView = {
    ...view,
    sections: Object.fromEntries(SECTION_KEYS.map((key) => [key, filterEntries(view.sections[key] ?? [], filters)])) as SpotlightView["sections"],
  };

  return (
    <div className="space-y-4">
      {scope.length > 0 && <SpotlightFilterBar fields={fields} total={total} filters={filters} onChange={change} />}
      {tab === "overview" ? (
        <Overview view={narrowed} date={date} groups={groups} filtered={filtered} />
      ) : (
        <>
          {tab === "news" && <NewsOverviewPanel overview={view.news_overview} entries={view.sections.news ?? []} visible={narrowed.sections.news} />}
          <SectionList entries={narrowed.sections[tab]} groups={groups} filtered={filtered} anchors={tab === "news"} />
        </>
      )}
    </div>
  );
}
