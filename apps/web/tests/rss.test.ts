import { describe, expect, it } from "vitest";

import { digestFeed } from "@/lib/rss";

describe("digestFeed", () => {
  it("lists digests as RSS items with escaped text and permalinks", () => {
    const xml = digestFeed("https://dx.example", [
      { digest_date: "2026-10-04", version: 1, status: "published", headline: "AI & <OS>", item_count: 12, generated_at: "2026-10-03T20:00:00Z" },
    ]);
    expect(xml).toContain('<rss version="2.0">');
    expect(xml).toContain("<title>2026-10-04 · AI &amp; &lt;OS&gt;</title>");
    expect(xml).toContain('<guid isPermaLink="true">https://dx.example/digests/2026-10-04</guid>');
    expect(xml).toContain("<pubDate>Sat, 03 Oct 2026 20:00:00 GMT</pubDate>");
  });
});
