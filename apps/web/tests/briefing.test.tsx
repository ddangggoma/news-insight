import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BriefingAside } from "@/components/reader/briefing-aside";
import { BriefingMain } from "@/components/reader/briefing-main";
import { BriefingPanes } from "@/components/reader/briefing-panes";
import type { PublicBriefing } from "@/lib/briefing-types";
import { formatBriefingDate } from "@/lib/format";
import type { ReaderItem } from "@/lib/reader-types";

const item = (id: number, field: string, impact: string): ReaderItem => ({
  id,
  url: `https://example.com/${id}`,
  title: `Item ${id}`,
  title_ko: `기사 ${id}`,
  summary_ko: [],
  keywords: [],
  field,
  themes: [],
  signal_type: "launch",
  impact,
  scope: "dx",
  relevance: 70,
  track: "news",
  source_name: "Src",
  region: "kr",
  published_at: null,
  first_seen_at: "2026-10-04T00:00:00Z",
  metrics: {},
  story: null,
});

const BRIEFING: PublicBriefing = {
  briefing_date: "2026-10-05",
  version: 1,
  published_at: "2026-10-04T20:00:00Z",
  headline: "헤드라인",
  tldr: ["첫째 요점", "둘째 요점", "셋째 요점"],
  overview: null,
  insights: [
    {
      title: "i",
      body: "b",
      item_ids: [1, 2],
      continuity: "continuing",
      previous_title: "어제 인사이트",
      companies: ["Qualcomm"],
      strength: { grade: "strong", outlets: 9, tracks: 2, regions: 2, vendor_share: 0, reason: "출처 9곳 · 트랙 2개 · 권역 2곳" },
    },
  ],
  continuing: [{ story_id: 7, item_id: 1, title: "사흘째 이어지는 이야기", days: 3, sources: 6 }],
  companies: [{ key: "qualcomm", label: "퀄컴", relation: "supplier", kind: "company", count: 2, item_ids: [1, 2] }],
  digest_tracks: [{ track: "news", summary: "뉴스 요약", categories: [{ category: "independent_media", headline: "범주 헤드라인", points: [{ text: "요점", item_ids: [1] }] }] }],
  sections: [{ track: "news", summary: null, items: [item(1, "ai", "opportunity"), item(2, "ai", "risk"), item(3, "display_av", "watch")] }],
  strategy: {
    personas: [
      { key: "ceo", name: "CEO", group: "executive", status: "insight", headline: "NPU 일정 점검", insight: "x", actions: [], item_ids: [1, 2] },
      { key: "cfo", name: "CFO", group: "executive", status: "no_signal", headline: "", insight: "", actions: [], item_ids: [] },
    ],
    report: null,
    review_verdict: null,
    dropped_claims: 0,
  },
  refs: [1, 2].map((id) => ({ id, title: `Item ${id}`, url: `https://example.com/${id}`, source_name: "Src", track: "news" })),
  gates_passed: 10,
  gates_total: 10,
  previous_date: null,
  next_date: null,
};

describe("briefing aside", () => {
  it("shows persona insights, citation counts and impact by field", () => {
    render(<BriefingAside briefing={BRIEFING} past={[]} />);

    expect(screen.getByText("NPU 일정 점검")).toBeInTheDocument();
    expect(screen.getByText(/신호 없음\(no_signal\) 1명/)).toBeInTheDocument();
    expect(screen.getAllByText(/인용 2회/)).toHaveLength(2);
    expect(screen.getByText("AI 모델·에이전트")).toBeInTheDocument();
    expect(screen.getByText("디스플레이·영상·오디오")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "지난 브리핑" })).not.toBeInTheDocument();
  });

  it("formats briefing dates as calendar days", () => {
    expect(formatBriefingDate("2026-10-05")).toBe("2026년 10월 5일 (월)");
  });
});

describe("briefing reading depth", () => {
  it("starts at one minute and opens insights, stories and the full summary on demand", async () => {
    const { container } = render(<BriefingPanes main={<BriefingMain briefing={BRIEFING} />} aside={<BriefingAside briefing={BRIEFING} past={[]} />} />);
    const wrapper = container.querySelector("[data-depth]");

    expect(wrapper).toHaveAttribute("data-depth", "one");
    expect(screen.getByText("첫째 요점")).toBeInTheDocument();
    expect(screen.getAllByText("퀄컴").length).toBeGreaterThan(0);
    expect(screen.getByText("근거 강함")).toHaveAttribute("title", "출처 9곳 · 트랙 2개 · 권역 2곳");
    expect(screen.getByText("이어짐")).toHaveAttribute("title", "이전: 어제 인사이트");
    expect(screen.getByText("3일째 · 출처 6곳")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "전체 수집 요약" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "심층" }));
    expect(wrapper).toHaveAttribute("data-depth", "deep");
  });
});
