import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BriefingAside } from "@/components/reader/briefing-aside";
import type { PublicBriefing } from "@/lib/briefing-types";
import { formatBriefingDate } from "@/lib/format";
import type { ReaderItem } from "@/lib/reader-types";

const item = (id: number, business: string, impact: string): ReaderItem => ({
  id,
  url: `https://example.com/${id}`,
  title: `Item ${id}`,
  title_ko: `기사 ${id}`,
  summary_ko: [],
  keywords: [],
  field: "mobile_edge",
  themes: [],
  businesses: [business],
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
  overview: null,
  insights: [{ title: "i", body: "b", item_ids: [1, 2] }],
  sections: [{ track: "news", summary: null, items: [item(1, "mx", "opportunity"), item(2, "mx", "risk"), item(3, "vd", "watch")] }],
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
  it("shows persona insights, citation counts and impact by business", () => {
    render(<BriefingAside briefing={BRIEFING} past={[]} />);

    expect(screen.getByText("NPU 일정 점검")).toBeInTheDocument();
    expect(screen.getByText(/신호 없음\(no_signal\) 1명/)).toBeInTheDocument();
    expect(screen.getAllByText(/인용 2회/)).toHaveLength(2);
    expect(screen.getByText("MX")).toBeInTheDocument();
    expect(screen.getByText("VD")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "지난 브리핑" })).not.toBeInTheDocument();
  });

  it("formats briefing dates as calendar days", () => {
    expect(formatBriefingDate("2026-10-05")).toBe("2026년 10월 5일 (월)");
  });
});
