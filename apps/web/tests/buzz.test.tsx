import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BuzzList, BuzzStrip } from "@/components/reader/buzz/buzz-list";
import { type BuzzCluster, headline, leadLabel, platformLabel } from "@/lib/buzz-types";

function cluster(overrides: Partial<BuzzCluster> = {}): BuzzCluster {
  return {
    id: 1,
    title: "클라우드 대규모 장애",
    summary: ["주요 리전에서 장애가 났다."],
    keywords: ["클라우드"],
    summarized: true,
    breaking: false,
    breaking_at: null,
    is_event: true,
    lead_minutes: null,
    first_seen_at: "2026-11-19T02:00:00Z",
    last_seen_at: "2026-11-19T02:40:00Z",
    crossed_at: "2026-11-19T02:30:00Z",
    authors: 4,
    posts: 5,
    platforms: ["fediverse", "hn"],
    heat: 2.4,
    score: 50,
    sample: [{ id: 9, title: "Anyone else down?", url: "https://hn.example/9", platform: "hn", author: "a", first_seen_at: "2026-11-19T02:00:00Z" }],
    news: [],
    ...overrides,
  };
}

describe("buzz signals", () => {
  it("says how far ahead of the news a breaking cluster was", () => {
    expect(leadLabel(cluster())).toBeNull();
    expect(leadLabel(cluster({ breaking: true }))).toBe("아직 뉴스 없음");
    expect(leadLabel(cluster({ breaking: true, lead_minutes: 15 }))).toBe("뉴스보다 15분 먼저");
    expect(leadLabel(cluster({ breaking: true, lead_minutes: 80 }))).toBe("뉴스보다 1시간 20분 먼저");
    expect(leadLabel(cluster({ breaking: true, lead_minutes: 120 }))).toBe("뉴스보다 2시간 먼저");
    expect(platformLabel("fediverse")).toBe("Mastodon");
    expect(platformLabel("tabnews")).toBe("tabnews");
  });

  it("puts breaking first and caps the band at three", () => {
    const rows = [cluster({ id: 1 }), cluster({ id: 2 }), cluster({ id: 3, breaking: true }), cluster({ id: 4 })];
    expect(headline(rows, 3).map((c) => c.id)).toEqual([3, 1, 2]);
  });

  it("lists clusters with their status, people, posts and news", () => {
    const breaking = cluster({ id: 7, breaking: true, title: "새 칩 공개", news: [{ id: 5, title: "칩 공개 기사", url: "u", source_name: "전자신문", first_seen_at: "2026-11-19T03:00:00Z" }], lead_minutes: 60 });
    render(<BuzzList clusters={[breaking, cluster({ summarized: false, title: "Anyone else down?" })]} now={new Date("2026-11-19T03:00:00Z")} />);
    const first = screen.getByRole("article", { name: "새 칩 공개" });
    expect(within(first).getByText("속보")).toBeInTheDocument();
    expect(within(first).getByText("뉴스보다 1시간 먼저")).toBeInTheDocument();
    expect(within(first).getByText("Mastodon · Hacker News — 4명 · 글 5건 · 반응 2.4")).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "칩 공개 기사" })).toHaveAttribute("href", "/items/5");
    expect(screen.getByText("(요약 작성 전, 원문)")).toBeInTheDocument();
  });

  it("says when nothing is buzzing and hides the band", () => {
    render(<BuzzList clusters={[]} />);
    expect(screen.getByText("지금 화제인 커뮤니티 이야기가 없습니다")).toBeInTheDocument();
    const { container } = render(<BuzzStrip clusters={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links the band into the page", () => {
    render(<BuzzStrip clusters={[cluster({ id: 3, breaking: true, title: "속보 제목" })]} />);
    const band = screen.getByRole("region", { name: "커뮤니티 화제·속보" });
    expect(within(band).getByRole("link", { name: "속보 제목" })).toHaveAttribute("href", "/buzz#c3");
    expect(within(band).getByRole("link", { name: "전체 보기 →" })).toHaveAttribute("href", "/buzz");
  });
});
