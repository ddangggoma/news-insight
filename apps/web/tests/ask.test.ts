import { describe, expect, it } from "vitest";

import { citationParts } from "@/lib/ask-types";

describe("citationParts", () => {
  it("turns known [n] into numbers and keeps the rest as text", () => {
    expect(citationParts("A [1][2]. B [9] C [3]", 3)).toEqual(["A ", 1, 2, ". B [9] C ", 3]);
  });

  it("returns the whole text when nothing is cited", () => {
    expect(citationParts("근거가 부족합니다.", 0)).toEqual(["근거가 부족합니다."]);
  });
});

describe("splitList", () => {
  it("splits on commas and lines without blanks or repeats", async () => {
    const { splitList } = await import("@/lib/dossier-types");
    expect(splitList("NPU, 온디바이스 AI,\nNPU, ,")).toEqual(["NPU", "온디바이스 AI"]);
  });
});

describe("changeLabel", () => {
  it("describes a change between two periods", async () => {
    const { changeLabel } = await import("@/lib/patent-types");
    expect([changeLabel(3, 1), changeLabel(1, 3), changeLabel(2, 0), changeLabel(0, 0), changeLabel(2, 2)]).toEqual(["+2", "-2", "새로", "–", "0"]);
  });
});
