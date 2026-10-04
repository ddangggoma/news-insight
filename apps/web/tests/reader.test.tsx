import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { LatestFallback } from "@/components/reader/latest-fallback";
import { ReaderCard } from "@/components/reader/reader-card";
import { TaxonomyTree } from "@/components/reader/taxonomy-tree";
import { formatBriefingDate } from "@/lib/format";
import { LIBRARY_KEY } from "@/lib/library";
import type { ReaderCard as Card } from "@/lib/reader-types";

const CARD: Card = {
  id: 42,
  title: "Samsung unveils Galaxy S30",
  title_ko: "삼성, 갤럭시 S30 공개",
  summary_ko: ["온디바이스 AI를 탑재했다."],
  keywords: ["삼성"],
  url: "https://example.com/s30",
  source_name: "The Verge",
  track: "news",
  category: "independent_media",
  region: "global_en",
  published_at: "2026-10-04T00:00:00Z",
  first_seen_at: "2026-10-04T00:05:00Z",
  field: "mobile_edge",
  themes: [],
  businesses: ["mx"],
  impact: "opportunity",
  relevance: 80,
  coverage: 3,
};

describe("reader", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders a card with coverage and topic links", () => {
    render(<ReaderCard card={CARD} />);

    expect(screen.getByRole("link", { name: "삼성, 갤럭시 S30 공개" })).toHaveAttribute("href", CARD.url);
    expect(screen.getByText("Samsung unveils Galaxy S30")).toBeInTheDocument();
    expect(screen.getByText(/3개 매체/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "MX" })).toHaveAttribute("href", "/topics?business=mx");
    expect(screen.getByRole("link", { name: "기회" })).toHaveAttribute("href", "/topics?impact=opportunity");
  });

  it("bookmarks and marks read in local storage", () => {
    render(<ReaderCard card={CARD} />);

    act(() => fireEvent.click(screen.getByRole("button", { name: "북마크" })));
    act(() => fireEvent.click(screen.getByRole("link", { name: "삼성, 갤럭시 S30 공개" })));

    const stored = JSON.parse(window.localStorage.getItem(LIBRARY_KEY) ?? "{}");
    expect(stored.version).toBe(1);
    expect(stored.bookmarks["42"].title).toBe("삼성, 갤럭시 S30 공개");
    expect(stored.read["42"]).toBeTruthy();
    expect(screen.getByRole("button", { name: "북마크 해제" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("읽음")).toBeInTheDocument();
  });

  it("lists every field and theme in the taxonomy tree", () => {
    render(
      <TaxonomyTree
        counts={{ window_days: 30, total: 5, fields: { ai_data: 5 }, themes: {}, businesses: { mx: 2 }, impacts: {} }}
        selected={{ theme: "ai_data__ai_agents" }}
      />,
    );

    expect(screen.getAllByRole("group")).toHaveLength(15);
    expect(screen.getByRole("link", { name: /AI 에이전트/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /MX · 모바일/ })).toHaveTextContent("2");
  });

  it("explains the schedule before the first briefing", () => {
    render(<LatestFallback cards={[CARD]} />);

    expect(screen.getByRole("heading", { name: "Daily IT Intelligence" })).toBeInTheDocument();
    expect(screen.getByText(/05:00 KST 정시 발행/)).toBeInTheDocument();
  });

  it("formats briefing dates as calendar days", () => {
    expect(formatBriefingDate("2026-10-05")).toBe("2026년 10월 5일 (월)");
  });
});
