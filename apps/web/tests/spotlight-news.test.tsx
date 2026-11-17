import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SpotlightBrowser } from "@/components/reader/spotlight/browser";
import { EntryRow } from "@/components/reader/spotlight/entry-row";
import { NewsOverviewPanel } from "@/components/reader/spotlight/news-overview";
import { type NewsOverview, type SpotlightEntry, type SpotlightView, entryAnchor, metricChips } from "@/lib/spotlight-types";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const entry = (key: string, rank: number, over: Partial<SpotlightEntry> = {}): SpotlightEntry => ({
  rank,
  stat_rank: rank,
  change: "same",
  change_by: 0,
  key,
  item_ids: [rank],
  title_ko: `제목 ${key}`,
  product_name: null,
  summary: "요약",
  why_hot: "왜 화제",
  rank_note: null,
  metrics: { source_count: 9, new_sources: 7, surge: 78, relevance: 80, community_mentions: 2, signal_type: "supply" },
  fallback: false,
  url: `https://example.com/${rank}`,
  ...over,
});

const news = [
  entry("story:1", 1, { insight: "패널 조달선을 다시 봐야 한다.", field: "display_av", field_label: "디스플레이·AV" }),
  entry("story:2", 2, { field: "ai", field_label: "AI" }),
  entry("story:3", 1, { group: "sustained", field: "ai", field_label: "AI" }),
];
const overview: NewsOverview = {
  themes: [
    { title: "AI 보안 경쟁", summary: "모델 공개가 취약점 발굴 경쟁으로 번졌다.", keys: ["story:2", "story:3"] },
    { title: "사라진 흐름", summary: "기사가 없다.", keys: ["story:9"] },
  ],
  areas: [{ area: "display", label: "디스플레이", insight: "OLED 전환이 빨라진다.", keys: ["story:1", "story:9"] }],
};
const viewOf = (over: Partial<SpotlightView> = {}): SpotlightView => ({
  date: "2026-11-13",
  generating: false,
  headline: "",
  benchmark_note: "",
  news_overview: overview,
  sections: { news, product: [], ai: [], oss: [], interview: [], community: [], research: [], patent: [] },
  available_dates: ["2026-11-13"],
  generated_at: "2026-11-13T20:10:00Z",
  ...over,
});

describe("news insight", () => {
  it("shows the 시사점 of a news entry under its reason", () => {
    render(<EntryRow entry={news[0]} />);
    expect(screen.getByText("시사점")).toBeInTheDocument();
    expect(screen.getByText("패널 조달선을 다시 봐야 한다.")).toBeInTheDocument();
  });

  it("shows no 시사점 line for an entry without one", () => {
    render(<EntryRow entry={news[1]} />);
    expect(screen.queryByText("시사점")).not.toBeInTheDocument();
  });

  it("labels today's coverage and hides the ranking inputs", () => {
    expect(metricChips(news[0].metrics)).toEqual(["보도 9곳", "오늘 7곳", "언급 2"]);
  });
});

describe("NewsOverviewPanel", () => {
  it("lists the themes and interest areas with their entries, skipping what the day no longer has", () => {
    render(<NewsOverviewPanel overview={overview} entries={news} visible={news} />);
    const themes = screen.getByRole("region", { name: /오늘의 구도/ });
    expect(within(themes).getByRole("heading", { name: /AI 보안 경쟁/ })).toBeInTheDocument();
    expect(within(themes).queryByText("사라진 흐름")).not.toBeInTheDocument();
    expect(within(themes).getByRole("link", { name: "제목 story:2" })).toHaveAttribute("href", `#${entryAnchor("story:2")}`);
    expect(within(themes).getByText("지속 주목 1위")).toBeInTheDocument();
    const areas = screen.getByRole("region", { name: /관심 분야별 정리/ });
    expect(within(areas).getByRole("heading", { name: "디스플레이" })).toBeInTheDocument();
    expect(within(areas).getByText("OLED 전환이 빨라진다.")).toBeInTheDocument();
    expect(within(areas).getAllByRole("listitem")).toHaveLength(2); // the area and its one remaining entry
  });

  it("renders nothing for a day published before the overview", () => {
    const { container } = render(<NewsOverviewPanel overview={null} entries={news} visible={news} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when none of its entries is listed", () => {
    const { container } = render(<NewsOverviewPanel overview={overview} entries={[]} visible={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("the news tab", () => {
  it("opens with the overview and gives each row the anchor the overview links to", () => {
    const { container } = render(<SpotlightBrowser view={viewOf()} tab="news" date={null} initial={{ field: null, group: null }} />);
    expect(screen.getByRole("region", { name: /오늘의 구도/ })).toBeInTheDocument();
    expect(container.querySelector(`#${entryAnchor("story:1")}`)).not.toBeNull();
  });

  it("keeps the overview when a filter narrows the list, without linking to hidden rows", () => {
    render(<SpotlightBrowser view={viewOf()} tab="news" date={null} initial={{ field: null, group: null }} />);
    fireEvent.click(screen.getByRole("button", { name: /디스플레이·AV/ }));
    const themes = screen.getByRole("region", { name: /오늘의 구도/ });
    expect(within(themes).getByText("제목 story:2")).toBeInTheDocument();
    expect(within(themes).queryByRole("link", { name: "제목 story:2" })).not.toBeInTheDocument();
  });

  it("has no overview on other tabs", () => {
    render(<SpotlightBrowser view={viewOf()} tab="overview" date={null} initial={{ field: null, group: null }} />);
    expect(screen.queryByRole("region", { name: /오늘의 구도/ })).not.toBeInTheDocument();
  });
});
