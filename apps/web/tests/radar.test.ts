import { describe, expect, it } from "vitest";

import {
  forceLayout,
  koreaGaps,
  koreaLagDays,
  netOpportunity,
  projected,
  rankSeries,
  regionTotals,
  specialization,
  formatChange,
  formatPoints,
  formatZ,
  initialFocus,
  parseFocus,
  periodLabel,
  quadrantOf,
  radarHref,
  researchShare,
  squarify,
  stageOf,
  volumeSplit,
  wordCloud,
} from "@/lib/radar";
import { formatDay } from "@/lib/format";
import { radarSignals } from "@/lib/radar-signals";
import { radarView } from "@/lib/radar-view";
import type { Radar, Topic } from "@/lib/reader-types";

const mix = (news = 0, community = 0, research_ip = 0, oss = 0) => ({ news, community, research_ip, oss });

function topic(key: string, counts: number[], patch: Partial<Topic> = {}): Topic {
  return {
    key,
    label: null,
    field: key.split("__")[0],
    counts,
    change: null,
    z: 0,
    state: null,
    sources: 3,
    tracks: mix(last(counts)),
    previous_tracks: mix(counts[counts.length - 2]),
    baseline_tracks: mix(counts.slice(0, -1).reduce((a, b) => a + b, 0)),
    impacts: { opportunity: 0, risk: 0, watch: 0 },
    regions: { kr: 0, global_en: last(counts), jp: 0, greater_china: 0, eu_other: 0 },
    first_seen: {},
    official: 0,
    effective_sources: 3,
    ...patch,
  };
}

function last(values: number[]): number {
  return values[values.length - 1];
}

const radar: Radar = {
  window: { kind: "week", key: "2026-W40", start: "2026-09-28T00:00:00+09:00", end: "2026-10-05T00:00:00+09:00", prev_key: "2026-W39", next_key: "2026-W41", is_current: true, elapsed: 0.5 },
  periods: ["2026-W37", "2026-W38", "2026-W39", "2026-W40"],
  kpis: { items: [10, 10, 12, 20], stories: [8, 8, 9, 15], sources: [5, 5, 6, 8], research: [3, 3, 4, 9], new_stories: 4, cross_track_stories: 1 },
  fields: [topic("ai", [4, 4, 5, 12], { z: 7 })],
  themes: [
    topic("ai__ai_agents", [2, 2, 2, 9], { z: 7, state: "surging", sources: 6 }),
    topic("robotics_mobility__humanoid_embodied", [0, 1, 1, 4], { z: 3, state: "rising", tracks: mix(1, 0, 2, 1) }),
    topic("display_av__xr_spatial", [5, 6, 5, 6], {
      z: 0.5,
      state: "steady",
      tracks: mix(5, 3, 0, 0),
      baseline_tracks: mix(6, 3, 8, 3),
    }),
    topic("connectivity__cellular_5g_6g", [6, 6, 6, 1], { z: -5, state: "falling" }),
  ],
  keywords: [
    topic("유리기판", [0, 0, 0, 3], { label: "유리기판", field: "semis", state: "new" }),
    topic("hbm4", [1, 1, 1, 4], { label: "HBM4", field: "semis", state: "rising" }),
    topic("온디바이스ai", [2, 2, 2, 5], { label: "온디바이스 AI", field: "ai", state: "rising" }),
  ],
  pairs: [
    { a: "hbm4", b: "온디바이스ai", count: 3, lift: 3.2, is_new: true },
    { a: "hbm4", b: "유리기판", count: 2, lift: 1.5, is_new: false },
  ],
  flows: { chains: 0, origins: {}, links: [] },
  engagement: { measured: 0, themes: [], top: [] },
  calendar: { start: "2026-07-13", days: [], anomalies: [] },
  field_links: [],
};

describe("radar URL state", () => {
  it("parses only known focus targets", () => {
    expect(parseFocus("theme:ai__ai_agents")).toEqual({ kind: "theme", key: "ai__ai_agents" });
    expect(parseFocus("field:ai")).toEqual({ kind: "field", key: "ai" });
    expect(parseFocus("keyword:온디바이스ai")).toEqual({ kind: "keyword", key: "온디바이스ai" });
    expect(parseFocus("keyword:a:b")).toEqual({ kind: "keyword", key: "a:b" });
    expect(parseFocus("theme:nope")).toBeNull();
    expect(parseFocus("field:")).toBeNull();
    expect(parseFocus("nope:ai")).toBeNull();
    expect(parseFocus(undefined)).toBeNull();
  });

  it("keeps filters and focus in the link and drops defaults", () => {
    expect(radarHref("week", "2026-W40", { scope: "relevant", signal: [], field: null, focus: null })).toBe("/radar/week/2026-W40");
    expect(radarHref("month", "2026-09", { scope: "all", signal: ["launch", "research"], field: "ai", focus: { kind: "keyword", key: "hbm4" } })).toBe(
      "/radar/month/2026-09?signal=launch&signal=research&field=ai&focus=keyword%3Ahbm4",
    );
  });

  it("reads the view from search params and ignores unknown values", () => {
    expect(radarView({ scope: "dx", signal: ["launch", "nope", "launch"], field: "ai", focus: "theme:ai__ai_agents" })).toEqual({
      scope: "dx",
      signal: ["launch"],
      field: "ai",
      focus: { kind: "theme", key: "ai__ai_agents" },
    });
    expect(radarView({ scope: "nope", signal: "research", field: "nope" })).toEqual({ scope: "relevant", signal: ["research"], field: null, focus: null });
  });
});

describe("radar numbers", () => {
  it("formats periods, changes, z and points", () => {
    expect(["2026-W05", "2026-09", "2026-Q3", "2026-10-04"].map(periodLabel)).toEqual(["W5", "9월", "Q3", "10/4"]);
    expect(formatChange(null)).toBe("–");
    expect(formatChange(-49.6)).toBe("▼50%");
    expect(formatZ(2.04)).toBe("+2.0σ");
    expect(formatZ(-1.26)).toBe("−1.3σ");
    expect(formatPoints(0.04)).toBe("±0%p");
    expect(formatPoints(-3.26)).toBe("−3.3%p");
  });

  it("derives research share, stage and quadrant", () => {
    expect(researchShare(mix(1, 1, 1, 1))).toBe(0.5);
    expect(researchShare(mix())).toBeNull();
    expect([0.6, 0.3, 0.1, null].map(stageOf)).toEqual(["research", "diffusion", "market", null]);
    const split = volumeSplit(radar.themes);
    expect(split).toBe(6);
    expect(radar.themes.map((t) => quadrantOf(t, split))).toEqual(["leading", "emerging", "mainstream", "niche"]);
  });

  it("opens the requested topic, else the theme with the strongest momentum", () => {
    expect(initialFocus(radar, { kind: "keyword", key: "hbm4" })).toEqual({ kind: "keyword", key: "hbm4" });
    expect(initialFocus(radar, null)).toEqual({ kind: "theme", key: "ai__ai_agents" });
  });
});

describe("radar regions, ranks and projection", () => {
  it("measures regional specialization and holds back thin cells", () => {
    const field = topic("ai", [0, 10], { regions: { kr: 6, global_en: 4, jp: 0, greater_china: 0, eu_other: 0 } });
    const other = topic("semis", [0, 10], { regions: { kr: 2, global_en: 7, jp: 1, greater_china: 0, eu_other: 0 } });
    const totals = regionTotals({ ...radar, fields: [field, other] });
    expect(totals).toEqual({ kr: 8, global_en: 11, jp: 1, greater_china: 0, eu_other: 0 });
    // Korea: 6 of 8 Korean reports vs 10 of 20 overall
    expect(specialization(field, "kr", totals)).toBeCloseTo(1.5);
    expect(specialization(field, "global_en", totals)).toBeCloseTo((4 / 11) / 0.5);
    // Japan would expect 0.5 reports: a zero there is not a gap
    expect(specialization(field, "jp", totals)).toBeNull();
    expect(specialization(field, "greater_china", totals)).toBeNull();
  });

  it("finds Korean gaps and lags", () => {
    const gaps = koreaGaps({
      ...radar,
      keywords: [
        topic("x", [0, 0, 0, 5], { state: "rising", regions: { kr: 0, global_en: 5, jp: 0, greater_china: 0, eu_other: 0 } }),
        topic("y", [0, 0, 0, 5], { state: "rising", regions: { kr: 1, global_en: 4, jp: 0, greater_china: 0, eu_other: 0 } }),
        topic("z", [0, 0, 0, 3], { state: "new" }),
        topic("w", [5, 5, 5, 6], { state: "steady" }),
        topic("v", [9, 9, 9, 7], { state: "falling" }),
      ],
    });
    // steady counts as long as it is not falling; Korean coverage or too few reports do not
    expect(gaps.map((k) => k.key)).toEqual(["w", "x"]);
    const lagged = topic("k", [0, 1], { first_seen: { global_en: "2026-09-01T00:00:00Z", jp: "2026-09-02T00:00:00Z", kr: "2026-09-04T12:00:00Z" } });
    expect(koreaLagDays(lagged)).toBe(3.5);
    expect(koreaLagDays(topic("k", [0, 1], { first_seen: { global_en: "2026-09-01T00:00:00Z" } }))).toBeNull();
  });

  it("projects the open window at the current pace, not too early and never for a closed one", () => {
    expect(projected(30, 0.5)).toBe(60);
    expect(projected(3, 0.1)).toBeNull();
    expect(projected(30, null)).toBeNull();
    expect(projected(30, 1)).toBeNull();
  });

  it("ranks topics per window and scores net opportunity", () => {
    const series = rankSeries(
      [topic("a", [5, 1, 9]), topic("b", [1, 5, 8]), topic("c", [0, 3, 1]), topic("d", [9, 9, 0])],
      2,
    );
    expect(series.map((row) => [row.topic.key, row.ranks])).toEqual([
      ["a", [2, 4, 1]],
      ["b", [3, 2, 2]],
    ]);
    expect(netOpportunity(topic("a", [1], { impacts: { opportunity: 6, risk: 2, watch: 2 } }))).toBeCloseTo(0.4);
    expect(netOpportunity(topic("a", [1]))).toBeNull();
  });
});

describe("radar layouts", () => {
  it("squarifies areas in proportion inside the box", () => {
    const rects = squarify([{ value: 6 }, { value: 3 }, { value: 1 }, { value: 0 }], { x: 0, y: 0, w: 100, h: 50 });
    expect(rects).toHaveLength(3);
    const area = rects.map((r) => r.w * r.h);
    expect(area[0] / area[2]).toBeCloseTo(6);
    expect(area.reduce((a, b) => a + b)).toBeCloseTo(5000);
    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(0);
      expect(r.x + r.w).toBeLessThanOrEqual(100.0001);
      expect(r.y + r.h).toBeLessThanOrEqual(50.0001);
    }
  });

  it("places cloud words inside the canvas without overlaps, biggest first", () => {
    const words = Array.from({ length: 30 }, (_, i) => ({ key: `k${i}`, text: i % 2 ? `기술 ${i}` : `Tech${i}`, weight: 30 - i }));
    const placed = wordCloud(words, 400, 240);
    expect(placed.length).toBeGreaterThan(15);
    expect(placed[0].key).toBe("k0");
    expect(placed[0].size).toBe(40);
    for (const [i, a] of placed.entries()) {
      expect(a.x - a.w / 2).toBeGreaterThanOrEqual(0);
      expect(a.y + a.h / 2).toBeLessThanOrEqual(240);
      for (const b of placed.slice(i + 1)) {
        expect(Math.abs(a.x - b.x) * 2 >= a.w + b.w || Math.abs(a.y - b.y) * 2 >= a.h + b.h).toBe(true);
      }
    }
  });

  it("lays out a network deterministically inside the margins", () => {
    const nodes = ["a", "b", "c", "d", "e"];
    const edges = [
      { a: "a", b: "b", weight: 3 },
      { a: "b", b: "c", weight: 1 },
      { a: "d", b: "e", weight: 2 },
    ];
    const one = forceLayout(nodes, edges, 300, 200, 20);
    const two = forceLayout(nodes, edges, 300, 200, 20);
    expect([...one.entries()]).toEqual([...two.entries()]);
    for (const { x, y } of one.values()) {
      expect(x).toBeGreaterThanOrEqual(20);
      expect(x).toBeLessThanOrEqual(280);
      expect(y).toBeGreaterThanOrEqual(20);
      expect(y).toBeLessThanOrEqual(180);
    }
    const distance = (p: string, q: string) => Math.hypot(one.get(p)!.x - one.get(q)!.x, one.get(p)!.y - one.get(q)!.y);
    expect(distance("a", "b")).toBeLessThan(distance("a", "e"));
  });
});

describe("radar signals", () => {
  it("renders the API's cards and drops tones it does not know", () => {
    const signals = radarSignals({
      ...radar,
      signals: [
        { tone: "surge", title: "AI 에이전트", detail: "9건", focus: { kind: "theme", key: "ai__ai_agents" }, score: 7 },
        { tone: "someday", title: "?", detail: "", focus: { kind: "theme", key: "x" }, score: 0 },
      ],
    });
    expect(signals).toEqual([{ tone: "surge", title: "AI 에이전트", detail: "9건", focus: { kind: "theme", key: "ai__ai_agents" } }]);
    expect(radarSignals(radar)).toEqual([]);
    expect(formatDay("2026-09-13T16:00:00Z")).toBe("2026.09.14");
  });
});
