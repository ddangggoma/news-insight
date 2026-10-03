import { describe, expect, it } from "vitest";

import { pageParam, param } from "@/lib/params";
import { pageHref, withQuery } from "@/lib/query";

describe("query helpers", () => {
  it("drops empty and 'all' values", () => {
    expect(withQuery("/api/admin/sources", { track: "news", region: "all", q: "", page: 2 })).toBe(
      "/api/admin/sources?track=news&page=2",
    );
    expect(withQuery("/x", {})).toBe("/x");
  });

  it("builds page links that keep filters", () => {
    expect(pageHref("/console/sources", { track: "oss", q: "ros" }, 3)).toBe(
      "/console/sources?track=oss&q=ros&page=3",
    );
    expect(pageHref("/console/sources", { page: "5" }, 1)).toBe("/console/sources");
  });

  it("reads search params safely", () => {
    expect(param({ track: "news" }, "track")).toBe("news");
    expect(param({ track: "all" }, "track")).toBeUndefined();
    expect(param({ track: ["a", "b"] }, "track")).toBe("a");
    expect(pageParam({ page: "4" })).toBe(4);
    expect(pageParam({ page: "-1" })).toBe(1);
  });
});
