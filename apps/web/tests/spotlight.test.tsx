import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DateSelect } from "@/components/reader/spotlight/date-select";
import { EntryRow } from "@/components/reader/spotlight/entry-row";
import { Overview } from "@/components/reader/spotlight/overview";
import { SectionList } from "@/components/reader/spotlight/section-list";
import { SpotlightTabs } from "@/components/reader/spotlight/spotlight-tabs";
import {
  SECTION_KEYS,
  SECTION_LABEL,
  type SpotlightEntry,
  type SpotlightView,
  isCalendarDay,
  metricChips,
  spotlightHref,
} from "@/lib/spotlight-types";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const base: SpotlightEntry = {
  rank: 1,
  stat_rank: 1,
  change: "same",
  change_by: 0,
  key: "n1",
  item_ids: [11],
  title_ko: "엔비디아, 새 가속기 공개",
  product_name: null,
  summary: "요약 두 줄",
  why_hot: "14개 매체가 동시에 보도",
  rank_note: null,
  metrics: { source_count: 14, community_mentions: 3 },
  fallback: false,
  url: "https://example.com/a",
};

const emptySections = (): SpotlightView["sections"] => ({ news: [], product: [], oss: [], interview: [], community: [], research: [], patent: [] });
const viewOf = (over: Partial<SpotlightView> = {}): SpotlightView => ({
  date: "2026-11-03",
  generating: false,
  headline: "오늘은 가속기 소식이 많았습니다",
  benchmark_note: "",
  sections: emptySections(),
  available_dates: ["2026-11-03", "2026-11-02"],
  generated_at: "2026-11-03T20:10:00Z",
  ...over,
});

describe("EntryRow", () => {
  it("shows the statistical rank when Opus moved the entry", () => {
    render(<EntryRow entry={{ ...base, rank: 2, stat_rank: 4 }} />);
    expect(screen.getByText("통계 4위")).toBeInTheDocument();
  });

  it("hides the statistical rank when it matches", () => {
    render(<EntryRow entry={base} />);
    expect(screen.queryByText(/통계/)).not.toBeInTheDocument();
  });

  it("marks fallback entries", () => {
    render(<EntryRow entry={{ ...base, fallback: true }} />);
    expect(screen.getByText("Opus 미작성")).toBeInTheDocument();
  });

  it("shows NEW and arrows", () => {
    const { rerender } = render(<EntryRow entry={{ ...base, change: "new" }} />);
    expect(screen.getByText("NEW")).toBeInTheDocument();
    expect(screen.getByLabelText("새로 진입")).toBeInTheDocument();
    rerender(<EntryRow entry={{ ...base, change: "up", change_by: 2 }} />);
    expect(screen.getByText("▲2")).toBeInTheDocument();
    expect(screen.getByLabelText("2계단 상승")).toHaveTextContent("▲2");
    rerender(<EntryRow entry={{ ...base, change: "down", change_by: 1 }} />);
    expect(screen.getByText("▼1")).toBeInTheDocument();
    expect(screen.getByLabelText("1계단 하락")).toHaveTextContent("▼1");
    rerender(<EntryRow entry={{ ...base, change: "same" }} />);
    expect(screen.queryByText(/NEW|▲|▼/)).not.toBeInTheDocument();
  });

  it("links the title to the source and falls back to plain text without a url", () => {
    const { rerender } = render(<EntryRow entry={base} />);
    const link = screen.getByRole("link", { name: "엔비디아, 새 가속기 공개" });
    expect(link).toHaveAttribute("href", "https://example.com/a");
    expect(link).toHaveAttribute("target", "_blank");
    rerender(<EntryRow entry={{ ...base, url: null }} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("엔비디아, 새 가속기 공개")).toBeInTheDocument();
  });

  it("shows summary, reason, rank note, metric chips and the product name", () => {
    render(<EntryRow entry={{ ...base, product_name: "Blackwell Ultra", rank_note: "통계보다 영향이 커서 올림", item_ids: [11, 12, 13] }} />);
    expect(screen.getByText("요약 두 줄")).toBeInTheDocument();
    expect(screen.getByText("14개 매체가 동시에 보도")).toBeInTheDocument();
    expect(screen.getByText("통계보다 영향이 커서 올림")).toBeInTheDocument();
    expect(screen.getByText("보도 14곳")).toBeInTheDocument();
    expect(screen.getByText("언급 3")).toBeInTheDocument();
    expect(screen.getByText("Blackwell Ultra")).toBeInTheDocument();
    expect(screen.getByText("같은 건 2건 더")).toBeInTheDocument();
  });
});

describe("metricChips", () => {
  it("labels known keys in Korean and formats numbers", () => {
    expect(
      metricChips({ source_count: 14, community_mentions: 3, mentions: 5, upvotes: 120, views: 480000, points: 412, comments: 230, stars: 1820 }),
    ).toEqual(["보도 14곳", "언급 3", "언급 5", "추천 120", "조회 480,000", "점수 412", "댓글 230", "별 1,820"]);
  });

  it("keeps unknown numeric keys with their own name, skips internal scores, and shows a platform as a label", () => {
    expect(metricChips({ forks: 7, community_z: 3.2, platform: "hackernews", note: "x", empty: 0 })).toEqual(["forks 7", "hackernews"]);
  });

  it("rounds fractions and tolerates no metrics", () => {
    expect(metricChips({ score: 12.6 })).toEqual(["점수 13"]);
    expect(metricChips({})).toEqual([]);
  });
});

describe("SectionList", () => {
  it("explains an empty section", () => {
    render(<SectionList entries={[]} />);
    expect(screen.getByText("오늘은 기준을 넘는 화제가 없습니다")).toBeInTheDocument();
  });

  it("lists the entries in order", () => {
    render(<SectionList entries={[base, { ...base, rank: 2, stat_rank: 2, key: "n2", title_ko: "둘째" }]} />);
    const list = screen.getAllByRole("list")[0]!;
    const titles = within(list).getAllByRole("link").map((link) => link.textContent);
    expect(titles).toEqual(["엔비디아, 새 가속기 공개", "둘째"]);
  });
});

describe("Overview", () => {
  it("shows the headline and the top three of each section with a link to its tab", () => {
    const sections = emptySections();
    sections.news = [1, 2, 3, 4].map((n) => ({ ...base, rank: n, stat_rank: n, key: `n${n}`, title_ko: `뉴스 ${n}` }));
    render(<Overview view={viewOf({ sections })} date="2026-11-03" />);
    expect(screen.getByText("오늘은 가속기 소식이 많았습니다")).toBeInTheDocument();
    expect(screen.getByText("뉴스 3")).toBeInTheDocument();
    expect(screen.queryByText("뉴스 4")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: SECTION_LABEL.news })).toHaveAttribute("href", "/spotlight?tab=news&date=2026-11-03");
    // every section gets a block, empty ones say so
    expect(screen.getAllByText("오늘은 기준을 넘는 화제가 없습니다")).toHaveLength(SECTION_KEYS.length - 1);
  });

  it("renders the empty state for every section when nothing is published yet", () => {
    render(<Overview view={viewOf({ date: null, headline: "", available_dates: [], generated_at: null })} date={null} />);
    expect(screen.getAllByText("오늘은 기준을 넘는 화제가 없습니다")).toHaveLength(SECTION_KEYS.length);
    expect(screen.getByRole("link", { name: SECTION_LABEL.patent })).toHaveAttribute("href", "/spotlight?tab=patent");
  });
});

describe("Overview links", () => {
  it("keep the day the reader asked for, and none for a plain /spotlight so it keeps rolling forward", () => {
    const { rerender } = render(<Overview view={viewOf()} date={null} />);
    expect(screen.getByRole("link", { name: SECTION_LABEL.news })).toHaveAttribute("href", "/spotlight?tab=news");
    rerender(<Overview view={viewOf()} date="2026-11-02" />);
    expect(screen.getByRole("link", { name: SECTION_LABEL.news })).toHaveAttribute("href", "/spotlight?tab=news&date=2026-11-02");
  });
});

describe("isCalendarDay", () => {
  it("accepts real days and refuses well-formed impossible ones", () => {
    expect(isCalendarDay("2026-11-03")).toBe(true);
    expect(isCalendarDay("2028-02-29")).toBe(true);
    expect(isCalendarDay("2026-02-29")).toBe(false);
    expect(isCalendarDay("2026-13-45")).toBe(false);
    expect(isCalendarDay("2026-00-10")).toBe(false);
    expect(isCalendarDay("2026-1-3")).toBe(false);
    expect(isCalendarDay("not-a-date")).toBe(false);
  });
});

describe("SpotlightTabs", () => {
  it("marks the open tab and keeps the date in every link", () => {
    render(<SpotlightTabs active="oss" date="2026-11-02" />);
    expect(screen.getByRole("link", { name: "오픈소스" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "전체" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "전체" })).toHaveAttribute("href", "/spotlight?date=2026-11-02");
    expect(screen.getByRole("link", { name: "뉴스" })).toHaveAttribute("href", "/spotlight?tab=news&date=2026-11-02");
    expect(within(screen.getByRole("navigation", { name: "주목 받는 보기" })).getAllByRole("link")).toHaveLength(1 + SECTION_KEYS.length);
  });

  it("defaults to the overview", () => {
    render(<SpotlightTabs active="overview" date={null} />);
    expect(screen.getByRole("link", { name: "전체" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "전체" })).toHaveAttribute("href", "/spotlight");
  });
});

describe("spotlightHref", () => {
  it("omits the default tab and an unset date", () => {
    expect(spotlightHref("overview", null)).toBe("/spotlight");
    expect(spotlightHref("research", null)).toBe("/spotlight?tab=research");
    expect(spotlightHref("overview", "2026-11-01")).toBe("/spotlight?date=2026-11-01");
  });
});

describe("DateSelect", () => {
  it("lists only published dates and navigates keeping the tab", () => {
    render(<DateSelect dates={["2026-11-03", "2026-11-02"]} current="2026-11-03" tab="news" />);
    const select = screen.getByRole("combobox", { name: "날짜" });
    expect(within(select).getAllByRole("option")).toHaveLength(2);
    fireEvent.change(select, { target: { value: "2026-11-02" } });
    expect(router.push).toHaveBeenCalledWith("/spotlight?tab=news&date=2026-11-02");
  });

  it("renders nothing when no date is published", () => {
    const { container } = render(<DateSelect dates={[]} current={null} tab="overview" />);
    expect(container).toBeEmptyDOMElement();
  });
});
