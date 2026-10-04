import { describe, expect, it } from "vitest";

import { changePercent, formatChange, heatLevel, heatRows, initialCell, parseCell } from "@/lib/radar";
import type { Radar } from "@/lib/reader-types";

const radar = {
  window: { kind: "week", key: "2026-W40", start: "", end: "", prev_key: "2026-W39", next_key: "2026-W41", is_current: true },
  kpis: { total: 5, previous_total: 1, new_stories: 1, cross_track_stories: 0, hottest: null },
  cells: [
    { field: "display_media", business: "vd", count: 3, previous: 0 },
    { field: "ai_data", business: "mx", count: 2, previous: 1 },
  ],
  momentum: [],
  hype: [],
  keywords: [],
} satisfies Radar;

describe("radar helpers", () => {
  it("scales heat with a square root and keeps small counts visible", () => {
    expect(heatLevel(0, 10)).toBe(0);
    expect(heatLevel(10, 10)).toBe(92);
    expect(heatLevel(1, 1000)).toBe(8);
  });

  it("formats changes against the previous window", () => {
    expect(changePercent(3, 0)).toBeNull();
    expect(changePercent(2, 1)).toBe(100);
    expect(formatChange(-49.6)).toBe("▼50%");
    expect(formatChange(null)).toBe("–");
    expect(formatChange(0.4)).toBe("±0%");
  });

  it("parses only known cells", () => {
    expect(parseCell("ai_data.mx")).toEqual({ field: "ai_data", business: "mx" });
    expect(parseCell("ai_data.none")).toEqual({ field: "ai_data", business: "none" });
    expect(parseCell("nope.mx")).toBeNull();
    expect(parseCell("ai_data.nope")).toBeNull();
  });

  it("orders rows by volume and opens the busiest cell without a hottest one", () => {
    expect(heatRows(radar, 2)).toEqual(["display_media", "ai_data"]);
    expect(heatRows(radar)).toHaveLength(15);
    expect(initialCell(radar, null)).toEqual({ field: "display_media", business: "vd" });
    expect(initialCell(radar, { field: "ai_data", business: "mx" })).toEqual({ field: "ai_data", business: "mx" });
  });
});
