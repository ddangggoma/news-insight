import { describe, expect, it } from "vitest";

import { digestFeed, podcastFeed, requestOrigin } from "@/lib/rss";

describe("digestFeed", () => {
  it("lists digests as RSS items with escaped text and permalinks", () => {
    const xml = digestFeed("https://dx.example", [
      { digest_date: "2026-10-04", version: 1, status: "published", headline: "AI & <OS>", item_count: 12, generated_at: "2026-10-03T20:00:00Z" },
    ]);
    expect(xml).toContain('<rss version="2.0">');
    expect(xml).toContain("<title>2026-10-04 · AI &amp; &lt;OS&gt;</title>");
    expect(xml).toContain('<guid isPermaLink="true">https://dx.example/briefings/2026-10-04</guid>');
    expect(xml).toContain("<pubDate>Sat, 03 Oct 2026 20:00:00 GMT</pubDate>");
  });
});

describe("podcastFeed", () => {
  it("lists spoken briefings as audio enclosures with durations", () => {
    const xml = podcastFeed("https://dx.example", [
      { briefing_date: "2026-10-06", headline: "NPU & 6G", url: "/media/briefings/2026-10-06-v1.m4a", seconds: 245, bytes: 1960000, generated_at: "2026-10-05T20:10:00Z" },
    ]);
    expect(xml).toContain('xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"');
    expect(xml).toContain('<enclosure url="https://dx.example/media/briefings/2026-10-06-v1.m4a" length="1960000" type="audio/mp4"/>');
    expect(xml).toContain("<itunes:duration>4:05</itunes:duration>");
    expect(xml).toContain("<title>2026-10-06 · NPU &amp; 6G</title>");
  });
});

describe("requestOrigin", () => {
  it("uses the forwarded host and scheme behind the proxy", () => {
    const proxied = new Request("https://0.0.0.0:3000/podcast.xml", { headers: { "x-forwarded-host": "222.0.0.1:8701", "x-forwarded-proto": "http" } });
    expect(requestOrigin(proxied)).toBe("http://222.0.0.1:8701");
    expect(requestOrigin(new Request("https://dx.example/feed.xml"))).toBe("https://dx.example");
  });
});
