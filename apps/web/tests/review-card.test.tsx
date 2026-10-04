import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { submitReview } = vi.hoisted(() => ({ submitReview: vi.fn(async () => {}) }));
vi.mock("@/app/console/actions", () => ({ submitReview }));

import { ReviewCard } from "@/components/console/review-card";
import type { ReviewItem } from "@/lib/types";

const VIEW: ReviewItem = {
  item: {
    id: 7,
    title: "Galaxy S30 launches",
    url: "https://example.com/7",
    source_key: "verge",
    source_name: "The Verge",
    track: "news",
    category: "independent_media",
    region: "global_en",
    published_at: null,
    first_seen_at: "2026-10-04T00:00:00Z",
    revision: 1,
    canary: true,
    metrics: {},
    title_ko: "갤럭시 S30 출시",
  },
  card: {
    title_ko: "갤럭시 S30 출시",
    summary_ko: ["요약"],
    keywords: ["삼성"],
    status: "ready",
    engine: "agy",
    model: "m",
    generated_at: "2026-10-04T00:10:00Z",
    scope: "dx",
    relevance: 77,
  },
  review: null,
};

describe("ReviewCard", () => {
  it("saves a verdict and marks it pressed", async () => {
    render(<ReviewCard view={VIEW} seed="abc" index={0} />);

    fireEvent.click(screen.getByRole("button", { name: /무관/ }));

    await waitFor(() => expect(submitReview).toHaveBeenCalledWith(7, "irrelevant", "", "abc"));
    expect(screen.getByRole("button", { name: /무관/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("갤럭시 S30 출시")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("DX 제품·기술")).toBeInTheDocument();
  });
});
