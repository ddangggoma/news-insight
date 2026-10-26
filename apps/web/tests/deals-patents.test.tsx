import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DealCard } from "@/components/reader/deal-card";
import { PatentCard } from "@/components/reader/patent-card";
import { type Deal, type DealView, dealBuckets, formatOriginal, formatUsdShort } from "@/lib/deal-types";
import { articleDate, type PatentView, patentSummary, periodLabel } from "@/lib/patent-types";
import type { ReaderItem } from "@/lib/reader-types";

const deal: Deal = {
  id: 1,
  kind: "investment",
  actor: "퀄컴",
  actor_key: "qualcomm",
  counterparty: "EdgeCo",
  counterparty_key: null,
  amount: 70_000_000_000,
  currency: "KRW",
  amount_usd: 50_000_000,
  stage: "시리즈 B",
  announced_on: null,
  occurred_on: "2026-10-03",
  summary: "퀄컴이 엣지 AI 스타트업에 투자했다.",
  item_id: 42,
  title: "퀄컴, 엣지 AI에 투자",
  source: "전자신문",
  url: "https://etnews.example/1",
  reports: 2,
};

function view(extra: Partial<DealView>): DealView {
  return { days: 30, total: 0, kinds: [], months: [], parties: [], pairs: [], deals: [], ...extra };
}

describe("deal helpers", () => {
  it("stacks weeks for short windows and folds rare kinds into 기타", () => {
    const { unit, buckets } = dealBuckets(
      view({
        days: 90,
        weeks: [{ week: "2026-09-28", counts: { investment: 2, licensing: 1, joint_venture: 1 }, usd: 3e7 }],
        months: [{ month: "2026-09", counts: { investment: 9 } }],
      }),
    );
    expect(unit).toBe("week");
    expect(buckets).toEqual([{ key: "2026-09-28", label: "9.28", total: 4, usd: 3e7, counts: { investment: 2, acquisition: 0, partnership: 0, ipo: 0, other: 2 } }]);
  });

  it("uses months for a year, and when an older API sends no weeks", () => {
    const months = [{ month: "2026-09", counts: { partnership: 3 } }];
    expect(dealBuckets(view({ days: 365, weeks: [], months })).unit).toBe("month");
    const { unit, buckets } = dealBuckets(view({ days: 30, months }));
    expect(unit).toBe("month");
    expect(buckets[0]).toMatchObject({ label: "26.09", total: 3 });
  });

  it("formats the original currency and short dollar sizes", () => {
    expect(formatOriginal(3e12, "KRW")).toBe("3조원");
    expect(formatOriginal(5e7, "USD")).toBe("");
    expect(formatUsdShort(1.5e8)).toBe("1.5억");
    expect(formatUsdShort(0)).toBe("–");
  });
});

describe("DealCard", () => {
  it("shows the parties, size, stage, date and evidence", () => {
    render(<DealCard deal={deal} companyHref={(key) => `/deals?company=${key}`} />);
    expect(screen.getByRole("link", { name: "퀄컴" })).toHaveAttribute("href", "/deals?company=qualcomm");
    expect(screen.getByText("EdgeCo").tagName).toBe("SPAN"); // not in the registry: no link
    expect(screen.getByText("약 5,000만 달러")).toBeInTheDocument();
    expect(screen.getByText("700억원")).toBeInTheDocument();
    expect(screen.getByText("시리즈 B")).toBeInTheDocument();
    expect(screen.getByText("2026.10.03")).toHaveAttribute("title", "발표일이 없어 근거 기사 날짜");
    expect(screen.getByRole("link", { name: "퀄컴, 엣지 AI에 투자" })).toHaveAttribute("href", "/items/42");
    expect(screen.getByText("보도 2건")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /원문/ })).toHaveAttribute("href", "https://etnews.example/1");
  });

  it("flags an implausible amount instead of presenting it", () => {
    render(<DealCard deal={{ ...deal, amount_usd: 2e12, currency: "USD", outlier: true }} companyHref={() => "/"} />);
    expect(screen.getByText("확인 필요, 합계 제외")).toBeInTheDocument();
  });
});

describe("patent helpers", () => {
  const trend = (key: string, current: number, previous: number) => ({ key, label: key, axis: "field" as const, counts: [previous, current], current, previous });
  const patents: PatentView = {
    kind: "month",
    periods: [
      { key: "2026-09", total: 10, office: 4 },
      { key: "2026-10", total: 15, office: 5 },
    ],
    nodes: [trend("ai", 6, 2), trend("display", 3, 3)],
    companies: [],
    recent: { items: [], total: 0, items_total: 0, page: 1, size: 20 },
  };

  it("sums the periods, the office share and the fastest riser", () => {
    const s = patentSummary(patents);
    expect(s.current?.total).toBe(15);
    expect(s.change).toBeCloseTo(0.5);
    expect(s.officeShare).toBeCloseTo(9 / 25);
    expect(s.riser?.key).toBe("ai");
  });

  it("labels months and quarters", () => {
    expect(periodLabel("2026-10")).toBe("26.10");
    expect(periodLabel("2026-Q3")).toBe("26 Q3");
  });

  it("dates an article by its own date first", () => {
    expect(articleDate({ occurred_at: "2026-10-01T00:00:00Z", published_at: "2026-10-02T00:00:00Z", first_seen_at: "2026-10-03T00:00:00Z" })).toBe("2026-10-01T00:00:00Z");
    expect(articleDate({ published_at: null, first_seen_at: "2026-10-03T00:00:00Z" })).toBe("2026-10-03T00:00:00Z");
  });
});

describe("PatentCard", () => {
  const item: ReaderItem = {
    id: 7,
    url: "https://epo.example/1",
    title: "Foldable hinge",
    title_ko: "폴더블 힌지 특허",
    summary_ko: ["힌지 구조를 다룬다."],
    keywords: [],
    field: "ai",
    themes: [],
    signal_type: "ip",
    impact: null,
    scope: "dx",
    relevance: 60,
    track: "research_ip",
    source_name: "EPO OPS",
    region: "global_en",
    published_at: "2026-09-30T03:00:00Z",
    first_seen_at: "2026-10-04T02:00:00Z",
    occurred_at: "2026-09-30T03:00:00Z",
    metrics: {},
    story: null,
  };

  it("links the title to the item and shows the article's date", () => {
    render(<PatentCard item={item} />);
    expect(screen.getByRole("link", { name: "폴더블 힌지 특허" })).toHaveAttribute("href", "/items/7");
    expect(screen.getByText("2026.09.30")).toBeInTheDocument();
    expect(screen.getByText("EPO OPS")).toBeInTheDocument();
  });
});
