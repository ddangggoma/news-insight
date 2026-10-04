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
import { radarSignals, shareDropZ } from "@/lib/radar-signals";
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
  it("reads surge, new, early, shift, link and cooling signals from the stats", () => {
    const signals = Object.fromEntries(radarSignals(radar).map((s) => [s.tone, s]));
    expect(signals.surge.title).toBe("AI 에이전트");
    expect(signals.surge.detail).toContain("직전 3주");
    expect(signals.new.focus).toEqual({ kind: "keyword", key: "유리기판" });
    expect(signals.early.title).toBe("휴머노이드·Embodied AI");
    expect(signals.shift.title).toBe("XR·공간컴퓨팅·AI 글래스");
    expect(signals.shift.detail).toContain("직전 3주 같은 시점 55% → 이번 0%");
    expect(signals.link.title).toBe("HBM4 × 온디바이스 AI");
    expect(signals.link.detail).toContain("첫 동시 언급");
    expect(signals.cool.title).toBe("5G-Adv·6G");
    expect(signals.hype).toBeUndefined();
  });

  it("flags chatter that outruns research, once per theme", () => {
    const hot = topic("platform_sw__device_os", [3, 3, 3, 9], { z: 0.8, tracks: mix(6, 2, 1, 0), baseline_tracks: mix(6, 3, 6, 0) });
    const signals = radarSignals({ ...radar, themes: [...radar.themes, hot] });
    const hype = signals.find((s) => s.tone === "hype")!;
    expect(hype.title).toBe("디바이스 OS·플랫폼");
    expect(hype.detail).toBe("뉴스·커뮤니티 8건으로 평소(3.0건)의 2.7배, 논문·오픈소스는 1건(평소 2.0건): 화제가 실체보다 앞섬");
    const keys = signals.filter((s) => s.focus.kind === "theme").map((s) => s.focus.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("flags thin sourcing and Korean gaps", () => {
    const narrow = topic("cloud_data__infra_ops", [2, 2, 2, 8], { z: 3, effective_sources: 1.6, baseline_tracks: mix(18) });
    const vendor = topic("platform_sw__device_os", [2, 2, 2, 6], { z: 2, official: 4, baseline_tracks: mix(15) });
    const abroad = topic("wasm", [0, 0, 1, 6], { label: "WASM", state: "rising", regions: { kr: 0, global_en: 6, jp: 0, greater_china: 0, eu_other: 0 } });
    const signals = radarSignals({ ...radar, themes: [narrow, vendor], keywords: [abroad], pairs: [] });
    const thin = signals.find((s) => s.tone === "thin")!;
    expect(thin.title).toBe("인프라 운영");
    expect(thin.detail).toContain("실효 출처 1.6곳");
    const gap = signals.find((s) => s.tone === "gap")!;
    expect(gap.title).toBe("WASM");
    expect(gap.detail).toContain("해외 6건");
    const onlyVendor = radarSignals({ ...radar, themes: [vendor], keywords: [], pairs: [] }).find((s) => s.tone === "thin")!;
    expect(onlyVendor.detail).toContain("뉴스 중 공식 발표 67%");
  });

  it("reads anomaly days, returning keywords, developer pull and new category links", () => {
    const signals = Object.fromEntries(
      radarSignals({
        ...radar,
        keywords: [
          topic("메타버스", [0, 0, 0, 4], { label: "메타버스", state: "new", returning: true, first_ever: "2026-01-01T00:00:00Z" }),
          topic("one ui 9", [0, 0, 2, 9], { label: "One UI 9", state: "surging", debut: true, first_ever: "2026-09-26T00:00:00Z" }),
        ],
        pairs: [],
        engagement: {
          measured: 30,
          themes: [
            { key: "display_av__xr_spatial", score: 80, items: 12 },
            { key: "ai__ai_agents", score: 20, items: 9 },
          ],
          top: [],
        },
        calendar: {
          start: "2026-07-13",
          days: [],
          anomalies: [
            { day: "2026-08-27", field: "ai", count: 40, expected: 13.5, z: 7.2, keywords: [] },
            { day: "2026-09-30", field: "platform_sw", count: 25, expected: 3.5, z: 11.5, keywords: [{ key: "갤럭시", label: "갤럭시", count: 9 }] },
          ],
        },
        field_links: [{ a: "frontier", b: "security", count: 3, previous: 0 }],
      }).map((s) => [s.tone, s]),
    );
    // only anomalies inside the window count, and the card opens the keyword behind them
    expect(signals.event.title).toBe("9/30 플랫폼·소프트웨어");
    expect(signals.event.detail).toBe("하루 25건, 평소 같은 요일 3.5건의 7.1배 · 갤럭시");
    expect(signals.event.focus).toEqual({ kind: "keyword", key: "갤럭시" });
    expect(signals.back.title).toBe("메타버스");
    expect(signals.new.title).toBe("One UI 9");
    expect(signals.new.detail).toContain("처음 보도된 지 8일");
    // XR: 6 of 20 mentions (30%) but 80% of the reactions; a theme already on another card is skipped
    expect(signals.pull.title).toBe("XR·공간컴퓨팅·AI 글래스");
    expect(signals.pull.detail).toContain("언급 비중 30%인데 반응(스타·포인트 증가) 비중 80%");
    expect(signals.link.title).toBe("미래 기술 × 보안·신뢰");
  });

  it("tests a drop in research share for significance", () => {
    const big = topic("a__b", [10, 10, 10, 30], { tracks: mix(24, 0, 6, 0), baseline_tracks: mix(10, 0, 20, 0) });
    const small = topic("a__b", [1, 1, 1, 3], { tracks: mix(3, 0, 0, 0), baseline_tracks: mix(1, 0, 2, 0) });
    // 67% → 20% over 30 reports each: z ≈ 3.6
    expect(shareDropZ(big)).toBeCloseTo(3.65, 1);
    expect(shareDropZ(small)).toBeLessThan(2);
    expect(formatDay("2026-09-13T16:00:00Z")).toBe("2026.09.14");
  });

  it("stays quiet on an empty radar", () => {
    expect(radarSignals({ ...radar, themes: [], keywords: [], pairs: [] })).toEqual([]);
  });
});
