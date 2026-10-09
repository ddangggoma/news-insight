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
