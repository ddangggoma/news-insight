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
    expect(withQuery("/x", { field: ["ai", "", "display_av"], q: "oled" })).toBe(
      "/x?field=ai&field=display_av&q=oled",
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
      field: ["ai", "nope", "ai"],
      signal: "launch",
      track: "oss",
      region: "mars",
      scope: "weird",
      period: "30d",
      sort: "coverage",
      page: "3",
      q: "  oled ",
    });
    expect(filters.field).toEqual(["ai"]);
    expect(filters.signal).toEqual(["launch"]);
    expect(filters.track).toEqual(["oss"]);
    expect(filters.region).toEqual([]);
    expect(filters.scope).toBe("relevant");
    expect(filters.period).toBe("30d");
    expect(filters.sort).toBe("coverage");
    expect(filters.page).toBe(3);
    expect(filters.q).toBe("oled");
  });

  it("builds links that toggle, remove and clear filters and reset the page", () => {
    const filters = parseReaderFilters({ field: "ai", period: "30d", page: "2" });
    expect(toggleHref(filters, "field", "display_av")).toBe("/?period=30d&field=ai&field=display_av");
    expect(toggleHref(filters, "field", "ai")).toBe("/?period=30d");
    expect(removeHref(filters, "field", "ai")).toBe("/?period=30d");
    expect(setHref(filters, "sort", "relevance")).toBe("/?period=30d&sort=relevance&field=ai");
    expect(setHref(filters, "period", "7d")).toBe("/?field=ai");
    expect(clearHref(filters)).toBe("/?period=30d");
  });

  it("lists active chips with labels", () => {
    const filters = parseReaderFilters({ field: "ai", signal: "launch", impact: "risk", q: "6G" });
    expect(activeChips(filters)).toEqual([
      { axis: "field", key: "ai", label: "AI 모델·에이전트" },
      { axis: "signal", key: "launch", label: "제품·기능 출시" },
      { axis: "impact", key: "risk", label: "위험" },
      { axis: "q", key: "6G", label: "“6G”" },
    ]);
  });

  it("carries company keys from chips to the API and the chips row", () => {
    const filters = parseReaderFilters({ company: ["qualcomm", "has space", "qualcomm"], period: "30d" });
    expect(filters.company).toEqual(["qualcomm"]);
    expect(apiParams(filters)).toMatchObject({ company: ["qualcomm"] });
    expect(activeChips(filters, { qualcomm: "퀄컴" })).toEqual([{ axis: "company", key: "qualcomm", label: "기업: 퀄컴" }]);
    expect(removeHref(filters, "company", "qualcomm")).toBe("/?period=30d");
    expect(clearHref(filters)).toBe("/?period=30d");
  });
});
