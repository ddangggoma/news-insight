import { describe, expect, it } from "vitest";

import {
  CATEGORY_LABEL,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatRelative,
  TRACK_LABEL,
} from "@/lib/format";

describe("format", () => {
  it("labels tracks and categories in Korean", () => {
    expect(TRACK_LABEL.research_ip).toBe("논문·특허");
    expect(CATEGORY_LABEL.official_vendor).toBe("빅테크·제조사 공식");
    expect(CATEGORY_LABEL.unknown_category).toBeUndefined();
  });

  it("formats KST date-times", () => {
    expect(formatDateTime("2026-10-03T00:30:00Z")).toBe("10.03 09:30");
    expect(formatDateTime(null)).toBe("—");
  });

  it("formats relative time in Korean", () => {
    const now = new Date("2026-10-03T12:00:00Z");
    expect(formatRelative("2026-10-03T11:57:00Z", now)).toBe("3분 전");
    expect(formatRelative("2026-10-03T14:00:00Z", now)).toBe("2시간 후");
    expect(formatRelative(null, now)).toBe("—");
  });

  it("formats numbers and percents", () => {
    expect(formatNumber(16168)).toBe("16,168");
    expect(formatPercent(0.255)).toBe("25.5%");
    expect(formatPercent(Number.NaN)).toBe("—");
  });
});
