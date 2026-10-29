import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RankBump } from "@/components/reader/radar/dynamics";
import { PositioningMatrix } from "@/components/reader/radar/landscape";
import { KpiStrip, SignalCards } from "@/components/reader/radar/overview";
import { baselineNote, baselineOf, baselineSpan, formatZ, quadrantOf, rankMove, rankSeries, type RadarView } from "@/lib/radar";
import type { Radar, RadarBaseline, Topic } from "@/lib/reader-types";

// 2026-10-27 audit: collection started on 2026-10-04, so most earlier windows are empty and
// every theme read "급상승" with z up to +41497σ

const mix = (news = 0, community = 0, research_ip = 0, oss = 0) => ({ news, community, research_ip, oss });
const view: RadarView = { scope: "all", signal: [], field: null, focus: null };

function topic(key: string, counts: number[], patch: Partial<Topic> = {}): Topic {
  return {
    key,
    label: null,
    field: key.split("__")[0],
    counts,
    change: null,
    z: null,
    state: null,
    sources: 3,
    tracks: mix(counts[counts.length - 1]),
    previous_tracks: mix(counts[counts.length - 2]),
    baseline_tracks: mix(0),
    impacts: { opportunity: 0, risk: 0, watch: 0 },
    regions: { kr: 0, global_en: counts[counts.length - 1], jp: 0, greater_china: 0, eu_other: 0 },
    first_seen: {},
    official: 0,
    effective_sources: 3,
    ...patch,
  };
}

const SHORT: RadarBaseline = { start: 7, windows: 0, required: 2, enough: false, collected_since: "2026-10-03T15:20:00Z" };
const ENOUGH: RadarBaseline = { start: 5, windows: 2, required: 2, enough: true, collected_since: "2026-10-03T15:20:00Z" };

function radar(baseline: RadarBaseline, patch: Partial<Radar> = {}): Radar {
  return {
    window: { kind: "month", key: "2026-10", start: "2026-10-01T00:00:00+09:00", end: "2026-11-01T00:00:00+09:00", prev_key: "2026-09", next_key: "2026-11", is_current: true, elapsed: 0.84 },
    periods: ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"],
    kpis: { items: [0, 0, 0, 0, 0, 0, 0, 900], stories: [0, 0, 0, 0, 0, 0, 0, 800], sources: [0, 0, 0, 0, 0, 0, 0, 300], research: [0, 0, 0, 0, 0, 0, 0, 90], new_stories: 0, cross_track_stories: 0 },
    fields: [topic("ai", [0, 0, 0, 0, 0, 0, 0, 500])],
    themes: [
      topic("ai__ai_agents", [0, 0, 0, 0, 0, 0, 0, 300]),
      topic("robotics_mobility__humanoid_embodied", [0, 0, 0, 0, 0, 0, 0, 120]),
      topic("display_av__xr_spatial", [0, 0, 0, 0, 0, 0, 0, 40]),
    ],
    keywords: [],
    pairs: [],
    flows: { chains: 0, origins: {}, links: [] },
    engagement: { measured: 0, themes: [], top: [] },
    calendar: { start: "2026-08-01", days: [], anomalies: [] },
    field_links: [],
    signals: [],
    baseline,
    ...patch,
  };
}

describe("radar baseline", () => {
  it("names the windows compared against and why scores are missing", () => {
    const short = radar(SHORT);
    expect(baselineSpan(short)).toBe("직전 0개월");
    expect(baselineNote(short)).toBe(
      "기준선 부족: 수집을 시작한 2026.10.04 이후 비교할 수 있는 직전 기간이 0개월뿐입니다(최소 2개월). 모멘텀(z)·상태·신호는 계산하지 않고 언급량만 보여 줍니다.",
    );
    expect(baselineNote(radar(ENOUGH))).toBeNull();
    // a response from before the field compares against every earlier window
    expect(baselineOf({ periods: ["a", "b", "c", "d"] })).toEqual({ start: 0, windows: 3, required: 2, enough: true, collected_since: null });
  });

  it("shows no z instead of a number, and no z is no momentum", () => {
    expect(formatZ(null)).toBe("–");
    expect(quadrantOf(topic("a__b", [0, 9], { z: null }), 2)).toBe("mainstream");
  });

  it("explains the positioning chart instead of pinning every point to the ceiling", () => {
    const { container } = render(<PositioningMatrix radar={radar(SHORT)} view={view} />);
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByText(/기준선 부족/)).toBeInTheDocument();
  });

  it("draws the positioning chart once z is there", () => {
    const scored = radar(ENOUGH, {
      themes: [topic("ai__ai_agents", [0, 0, 0, 0, 0, 3, 3, 9], { z: 3.5 }), topic("display_av__xr_spatial", [0, 0, 0, 0, 0, 5, 6, 5], { z: -0.2 })],
    });
    const { container } = render(<PositioningMatrix radar={scored} view={view} />);
    expect(container.querySelectorAll("svg").length).toBeGreaterThan(0);
  });

  it("says why there are no signal cards and no state counts", () => {
    render(<SignalCards radar={radar(SHORT)} view={view} />);
    expect(screen.getByText(/기준선 부족/)).toBeInTheDocument();
    render(<KpiStrip radar={radar(SHORT)} />);
    expect(screen.getAllByText("기준선 부족으로 판정 안 함")).toHaveLength(2);
    expect(screen.getAllByText("직전 기간은 수집 전이라 비교 안 함").length).toBeGreaterThan(0);
  });
});

describe("radar KPI deltas", () => {
  it("compare a window in progress with the same point of the previous one", () => {
    const week = radar(ENOUGH, {
      window: { kind: "week", key: "2026-W44", start: "2026-10-26T00:00:00+09:00", end: "2026-11-02T00:00:00+09:00", prev_key: "2026-W43", next_key: "2026-W45", is_current: true, elapsed: 0.19 },
      periods: ["2026-W37", "2026-W38", "2026-W39", "2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"],
      // 19 % into the week: 27k so far against 141k for all of last week, 26k at this point
      kpis: {
        items: [0, 0, 0, 85000, 190000, 151000, 141000, 27000],
        stories: [0, 0, 0, 1, 1, 1, 1, 1],
        sources: [0, 0, 0, 300, 400, 400, 400, 350],
        research: [0, 0, 0, 8500, 19000, 15100, 14100, 2700],
        new_stories: 0,
        cross_track_stories: 0,
        paced: { items: [0, 0, 0, 85000, 36000, 28000, 26000, 27000], sources: [0, 0, 0, 300, 360, 350, 350, 350], research: [0, 0, 0, 8500, 3600, 2800, 2600, 2700] },
      },
    });
    render(<KpiStrip radar={week} />);
    expect(screen.getAllByText("직전 기간 같은 시점 대비").length).toBeGreaterThan(0);
    expect(screen.getByText("▲4%")).toBeInTheDocument(); // 27k vs 26k, not ▼81% vs 141k
  });
});

describe("radar rank bump", () => {
  it("does not count a theme absent from the first window as climbing from 11th", () => {
    expect(rankMove([null, null, null, 4, 3, 2], 11)).toBe(2);
    expect(rankMove([null, null, null, null, null, 1], 11)).toBeNull();
    expect(rankMove([12, 5, 1], 11)).toBe(10);
  });

  it("marks a newcomer in the tooltip rather than as a big climber", () => {
    const themes = [
      topic("ai__ai_agents", [0, 0, 0, 0, 0, 0, 5, 9]),
      topic("display_av__xr_spatial", [0, 0, 0, 0, 0, 0, 0, 7]),
      topic("connectivity__cellular_5g_6g", [0, 0, 0, 0, 0, 0, 8, 3]),
    ];
    expect(rankSeries(themes).map((row) => rankMove(row.ranks, 11))).toEqual([1, null, -2]);
    const { container } = render(<RankBump radar={radar(ENOUGH, { themes })} view={view} />);
    const tips = [...container.querySelectorAll("[data-tip]")].map((g) => g.getAttribute("data-tip"));
    expect(tips.find((tip) => tip?.startsWith("XR"))).toMatch(/새로 등장/);
  });
});
