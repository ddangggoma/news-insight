import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { DigestBanner } from "@/components/reader/digest-banner";
import { InsightPanel } from "@/components/reader/insight-panel";
import { StoryRow } from "@/components/reader/story-row";
import { parseReaderFilters } from "@/lib/reader-filters";
import type { Insights, ReaderItem } from "@/lib/reader-types";

const item: ReaderItem = {
  id: 42,
  url: "https://example.com/a",
  title: "Phone makers move AI agents into the OS layer",
  title_ko: "에이전트 기능을 OS 계층으로",
  summary_ko: ["여러 제조사가 발표했습니다.", "권한 모델도 바뀝니다."],
  keywords: ["에이전트 OS", "AI"],
  field: "ai",
  themes: ["ai__ai_agents"],
  signal_type: "research",
  impact: "opportunity",
  scope: "dx",
  relevance: 88,
  track: "news",
  source_name: "The Verge",
  region: "global_en",
  published_at: null,
  first_seen_at: "2026-10-04T02:00:00Z",
  metrics: { stars: 2312 },
  story: { id: 7, item_count: 3, source_count: 2, tracks: ["news"] },
};

describe("StoryRow", () => {
  it("links the Korean title to the article and shows its classification and coverage", () => {
    render(<StoryRow item={item} now={new Date("2026-10-04T03:00:00Z")} />);
    expect(screen.getByRole("link", { name: "에이전트 기능을 OS 계층으로" })).toHaveAttribute("href", "/items/42");
    expect(screen.getByText("AI 모델·에이전트")).toBeInTheDocument();
    expect(screen.getByText("연구·논문")).toBeInTheDocument();
    expect(screen.getByText("기회")).toBeInTheDocument();
    expect(screen.getByText("관련 보도 3건 · 매체 2곳")).toBeInTheDocument();
    expect(screen.getByText("★ 2,312")).toBeInTheDocument();
    expect(screen.getByText("여러 제조사가 발표했습니다. 권한 모델도 바뀝니다.")).toHaveClass("text-ink-2");
  });
});

describe("InsightPanel", () => {
  const insights: Insights = {
    total: 10,
    previous_total: 4,
    keywords: [
      { key: "ai에이전트", label: "AI 에이전트", count: 10, previous: 3, change: 233.3, is_new: false },
      { key: "wifi8", label: "Wi-Fi 8", count: 4, previous: 0, change: null, is_new: true },
      { key: "oled", label: "OLED", count: 2, previous: 4, change: -50, is_new: false },
    ],
    related_keywords: ["번인"],
    fields: [{ key: "ai", count: 6 }],
    signal_types: [{ key: "research", count: 5 }],
    impacts: [{ key: "opportunity", count: 7 }, { key: "risk", count: 3 }],
  };

  it("shows keyword changes as whole percents and marks new keywords", () => {
    render(<InsightPanel insights={insights} filters={parseReaderFilters({})} />);
    expect(screen.getByText("▲233%")).toBeInTheDocument();
    expect(screen.getByText("▼50%")).toBeInTheDocument();
    expect(screen.getByText("신규")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI 에이전트" })).toHaveAttribute("href", "/?q=AI+%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8");
    expect(screen.getByText("60%")).toBeInTheDocument();
  });
});

describe("DigestBanner", () => {
  beforeEach(() => window.localStorage.clear());

  it("hides that day's digest after closing, and stays hidden", () => {
    const { unmount } = render(<DigestBanner date="2026-10-04" headline="오늘의 헤드라인" insights={["a", "b"]} />);
    fireEvent.click(screen.getByRole("button", { name: "다이제스트 닫기" }));
    expect(screen.queryByText("오늘의 헤드라인")).not.toBeInTheDocument();
    unmount();
    render(<DigestBanner date="2026-10-04" headline="오늘의 헤드라인" insights={[]} />);
    expect(screen.queryByText("오늘의 헤드라인")).not.toBeInTheDocument();
    render(<DigestBanner date="2026-10-05" headline="다음 날" insights={[]} />);
    expect(screen.getByText("다음 날")).toBeInTheDocument();
  });
});
