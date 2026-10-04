import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NewsCard } from "@/components/console/news-card";
import type { CardView } from "@/lib/types";

const VIEW: CardView = {
  item: {
    id: 42,
    title: "Samsung unveils Galaxy S30",
    url: "https://example.com/s30",
    source_key: "the-verge",
    source_name: "The Verge",
    track: "news",
    category: "independent_media",
    region: "global_en",
    published_at: "2026-10-04T00:00:00Z",
    first_seen_at: "2026-10-04T00:05:00Z",
    revision: 1,
    canary: true,
    metrics: {},
    title_ko: "삼성, 갤럭시 S30 공개",
  },
  card: {
    title_ko: "삼성, 갤럭시 S30 공개",
    summary_ko: ["온디바이스 AI를 탑재했다.", "3월 출시된다."],
    keywords: ["삼성", "갤럭시"],
    status: "ready",
    engine: "agy",
    model: "gemini",
    generated_at: "2026-10-04T00:10:00Z",
    field: "mobile_edge",
    themes: ["mobile_edge__smartphone_compute"],
    businesses: ["mx"],
    impact: "opportunity",
    scope: "dx",
    relevance: 82,
  },
  story: { id: 9, item_count: 4, source_count: 3, tracks: ["news"], is_representative: true },
};

describe("NewsCard", () => {
  it("shows the Korean card with original title, summary, keywords and source link", () => {
    render(<NewsCard view={VIEW} now={new Date("2026-10-04T02:00:00Z")} />);

    expect(screen.getByRole("link", { name: "삼성, 갤럭시 S30 공개" })).toHaveAttribute("href", "/console/items/42");
    expect(screen.getByText("Samsung unveils Galaxy S30")).toBeInTheDocument();
    expect(screen.getByText("3월 출시된다.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "#삼성" })).toHaveAttribute("href", "/console/cards?q=%EC%82%BC%EC%84%B1");
    expect(screen.getByRole("link", { name: /원문/ })).toHaveAttribute("href", "https://example.com/s30");
    expect(screen.getByText("2시간 전")).toBeInTheDocument();
    expect(screen.getByText("MX")).toBeInTheDocument();
    expect(screen.getByText("기회")).toBeInTheDocument();
    expect(screen.getByText("스마트폰·모바일 컴퓨팅")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "관련 3건" })).toHaveAttribute("href", "/console/stories?focus=9");
  });

  it("renders the summary in the readable body ink, not muted grey", () => {
    render(<NewsCard view={VIEW} now={new Date("2026-10-04T02:00:00Z")} />);

    const summary = screen.getByRole("list");
    expect(summary).toHaveClass("text-ink-2");
    expect(summary).not.toHaveClass("text-muted-foreground");
  });

  it("falls back to the original title and hides empty sections", () => {
    render(
      <NewsCard view={{ item: { ...VIEW.item, title_ko: null }, card: { ...VIEW.card, title_ko: null, summary_ko: [], keywords: [] } }} />,
    );

    expect(screen.getByRole("link", { name: "Samsung unveils Galaxy S30" })).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
