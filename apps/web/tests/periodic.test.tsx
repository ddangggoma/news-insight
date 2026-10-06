import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PeriodicLinks, PeriodicView, periodTitle } from "@/components/reader/periodic-view";
import type { PublicPeriodic } from "@/lib/briefing-types";

const PERIOD: PublicPeriodic = {
  kind: "week",
  key: "2026-W40",
  label: "주간 브리핑",
  headline: "주간 헤드라인",
  period_start: "2026-09-28",
  period_end: "2026-10-04",
  version: 1,
  days: 7,
  generated_at: "2026-10-04T20:10:00Z",
  content: {
    headline: "주간 헤드라인",
    tldr: ["첫째", "둘째", "셋째"],
    overview: "개요",
    trends: [{ title: "온디바이스 AI 확산", body: "본문", item_ids: [1, 2], trajectory: "rising", companies: ["삼성전자"] }],
    companies: [{ name: "퀄컴", summary: "NPU 발표", item_ids: [2] }],
    watch_next: ["다음 주 발표"],
    actions: ["벤치마크 표 갱신"],
  },
  refs: [1, 2].map((id) => ({ id, title: `Item ${id}`, url: `https://example.com/${id}`, source_name: "Src", track: "news" as const })),
  daily: [{ briefing_date: "2026-09-28", headline: "월요일 헤드라인" }],
  previous_key: "2026-W39",
  next_key: null,
};

describe("periodic briefing", () => {
  it("names weeks and months in Korean", () => {
    expect(periodTitle("week", "2026-W40")).toBe("2026년 40주차 주간 브리핑");
    expect(periodTitle("month", "2026-09")).toBe("2026년 9월 월간 브리핑");
  });

  it("shows trends with trajectory, companies, next signals, actions and the daily list", () => {
    render(<PeriodicView period={PERIOD} />);
    expect(screen.getByRole("heading", { level: 1, name: "주간 헤드라인" })).toBeInTheDocument();
    expect(screen.getByText("커지는 중")).toBeInTheDocument();
    expect(screen.getByText("NPU 발표")).toBeInTheDocument();
    expect(screen.getByText("다음 주 발표")).toBeInTheDocument();
    expect(screen.getByText("벤치마크 표 갱신")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /월요일 헤드라인/ })).toHaveAttribute("href", "/briefings/2026-09-28");
    expect(screen.getByRole("link", { name: /39주차/ })).toHaveAttribute("href", "/briefings/weekly/2026-W39");
  });

  it("links weekly and monthly entries", () => {
    render(<PeriodicLinks entries={[{ kind: "month", key: "2026-09", headline: "9월" }]} />);
    expect(screen.getByRole("link", { name: /9월 월간 브리핑/ })).toHaveAttribute("href", "/briefings/monthly/2026-09");
  });
});
