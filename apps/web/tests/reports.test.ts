import { describe, expect, it } from "vitest";

import { isWaiting, waitingText } from "@/lib/report-types";

describe("trend report status", () => {
  it("says where a waiting report is", () => {
    expect(waitingText({ status: "queued", position: 1 })).toContain("곧 작성을 시작");
    expect(waitingText({ status: "queued", position: 3 })).toContain("앞에 2건");
    expect(waitingText({ status: "running", position: null })).toContain("쓰고 있습니다");
    expect(waitingText({ status: "ready", position: null })).toBe("");
  });

  it("refreshes only while queued or running", () => {
    expect(isWaiting("queued") && isWaiting("running")).toBe(true);
    expect(isWaiting("ready") || isWaiting("failed")).toBe(false);
  });
});
