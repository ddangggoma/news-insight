import { describe, expect, it } from "vitest";

import { withQuery } from "@/lib/query";
import {
  activeChips,
  apiParams,
  clearHref,
  parseReaderFilters,
  removeHref,
  setHref,
  toggleHref,
} from "@/lib/reader-filters";

describe("withQuery arrays", () => {
  it("repeats keys for array values and skips empty entries", () => {
    expect(withQuery("/x", { field: ["ai_data", "", "display_media"], q: "oled" })).toBe(
      "/x?field=ai_data&field=display_media&q=oled",
    );
    expect(withQuery("/x", { field: [] })).toBe("/x");
  });
});

describe("reader filters", () => {
  it("uses defaults for an empty URL", () => {
    const filters = parseReaderFilters({});
    expect(filters).toMatchObject({ scope: "relevant", period: "7d", sort: "recent", page: 1, q: "" });
    expect(filters.field).toEqual([]);
    expect(apiParams(filters)).toEqual({ scope: "relevant", period: "7d", sort: "recent", page: 1 });
  });

  it("keeps known values, drops unknown ones and duplicates", () => {
    const filters = parseReaderFilters({
      field: ["ai_data", "nope", "ai_data"],
      business: "mx",
      track: "oss",
      region: "mars",
      scope: "weird",
      period: "30d",
      sort: "coverage",
      page: "3",
      q: "  oled ",
    });
    expect(filters.field).toEqual(["ai_data"]);
    expect(filters.business).toEqual(["mx"]);
    expect(filters.track).toEqual(["oss"]);
    expect(filters.region).toEqual([]);
    expect(filters.scope).toBe("relevant");
    expect(filters.period).toBe("30d");
    expect(filters.sort).toBe("coverage");
    expect(filters.page).toBe(3);
    expect(filters.q).toBe("oled");
  });

  it("builds links that toggle, remove and clear filters and reset the page", () => {
    const filters = parseReaderFilters({ field: "ai_data", period: "30d", page: "2" });
    expect(toggleHref(filters, "field", "display_media")).toBe("/?period=30d&field=ai_data&field=display_media");
    expect(toggleHref(filters, "field", "ai_data")).toBe("/?period=30d");
    expect(removeHref(filters, "field", "ai_data")).toBe("/?period=30d");
    expect(setHref(filters, "sort", "relevance")).toBe("/?period=30d&sort=relevance&field=ai_data");
    expect(setHref(filters, "period", "7d")).toBe("/?field=ai_data");
    expect(clearHref(filters)).toBe("/?period=30d");
  });

  it("lists active chips with labels", () => {
    const filters = parseReaderFilters({ field: "ai_data", business: "mx", impact: "risk", q: "6G" });
    expect(activeChips(filters)).toEqual([
      { axis: "field", key: "ai_data", label: "AI·데이터" },
      { axis: "business", key: "mx", label: "MX · 모바일·온디바이스 AI" },
      { axis: "impact", key: "risk", label: "위험" },
      { axis: "q", key: "6G", label: "“6G”" },
    ]);
  });
});
