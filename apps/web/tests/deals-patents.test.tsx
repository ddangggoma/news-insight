import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DealCard } from "@/components/reader/deal-card";
import { type Deal, type DealView, dealBuckets, formatOriginal, formatUsdShort } from "@/lib/deal-types";

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
