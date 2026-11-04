import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SpotlightBrowser } from "@/components/reader/spotlight/browser";
import { DateSelect } from "@/components/reader/spotlight/date-select";
import { GeneratingBand } from "@/components/reader/spotlight/generating-band";
import { EntryRow } from "@/components/reader/spotlight/entry-row";
import { Overview } from "@/components/reader/spotlight/overview";
import { SectionList } from "@/components/reader/spotlight/section-list";
import { SpotlightTabs } from "@/components/reader/spotlight/spotlight-tabs";
import {
  SECTION_KEYS,
  SECTION_LABEL,
  type SpotlightEntry,
  type SpotlightView,
  fieldCounts,
  filterEntries,
  isCalendarDay,
  metricChips,
  parseFilters,
  spotlightHref,
  trendChip,
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

const emptySections = (): SpotlightView["sections"] => ({ news: [], product: [], ai: [], oss: [], interview: [], community: [], research: [], patent: [] });
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

  it("labels the product group size and the Hugging Face trending rank in Korean", () => {
    expect(metricChips({ group_size: 3, trending: 12 })).toEqual(["묶음 3건", "트렌딩 12"]);
  });

  it("names the trending list a backfilled open-source entry came from", () => {
    expect(metricChips({ rank: 3, stars: 900, basis: "github_daily", trend_rank: 3 })).toEqual(["GitHub 트렌딩 3위", "별 900"]);
    expect(metricChips({ rank: 7, basis: "github_weekly", trend_rank: 7 })).toEqual(["GitHub 주간 트렌딩 7위"]);
    expect(metricChips({ trending: 40, basis: "hf_trending", trend_rank: 2 })).toEqual(["HF 트렌딩", "트렌딩 40"]);
    expect(trendChip({ basis: "other" })).toBeNull();
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

describe("AI 모델·서비스", () => {
  it("has its own tab right after 제품, and the leaderboards keep theirs at the end", () => {
    render(<SpotlightTabs active="ai" date={null} />);
    const labels = within(screen.getByRole("navigation", { name: "주목 받는 보기" }))
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(labels).toEqual(["전체", "뉴스", "제품", "AI 모델·서비스", "오픈소스", "인터뷰·발언", "커뮤니티", "연구", "특허", "AI 모델"]);
    expect(screen.getByRole("link", { name: "AI 모델·서비스" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "AI 모델·서비스" })).toHaveAttribute("href", "/spotlight?tab=ai");
  });

  it("shows its top three on the overview", () => {
    const sections = emptySections();
    sections.ai = [1, 2, 3, 4].map((n) => ({ ...base, rank: n, stat_rank: n, key: `a${n}`, title_ko: `모델 ${n}` }));
    render(<Overview view={viewOf({ sections })} date={null} />);
    const block = screen.getByRole("heading", { level: 2, name: "AI 모델·서비스" }).closest("section")!;
    expect(within(block).getAllByRole("listitem")).toHaveLength(3);
    expect(within(block).getByText("모델 3")).toBeInTheDocument();
    expect(screen.queryByText("모델 4")).not.toBeInTheDocument();
  });

  it("labels a leaderboard entry by its site and rank", () => {
    expect(metricChips({ basis: "benchmark", site: "LMArena", board: "text", rank: 3, from: 9 })).toEqual(["LMArena 3위"]);
  });

  it("tolerates an API that has no ai section yet", () => {
    const { ai: _omitted, ...older } = emptySections();
    render(<Overview view={viewOf({ sections: older as SpotlightView["sections"] })} date={null} />);
    expect(screen.getAllByText("오늘은 기준을 넘는 화제가 없습니다")).toHaveLength(SECTION_KEYS.length);
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

describe("GeneratingBand", () => {
  it("says only that today's list is being generated, as a status", () => {
    render(<GeneratingBand />);
    expect(screen.getByRole("status")).toHaveTextContent(/^오늘 목록 생성 중$/);
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
    expect(screen.getByRole("link", { name: "AI 모델" })).toHaveAttribute("href", "/spotlight?tab=models&date=2026-11-02");
    // 전체, one per section, AI 모델
    expect(within(screen.getByRole("navigation", { name: "주목 받는 보기" })).getAllByRole("link")).toHaveLength(2 + SECTION_KEYS.length);
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

const sustainedEntry = (n: number, over: Partial<SpotlightEntry> = {}): SpotlightEntry => ({
  ...base,
  group: "sustained",
  rank: n,
  stat_rank: n,
  key: `s${n}`,
  title_ko: `지속 ${n}`,
  ...over,
});
const nowEntry = (n: number, over: Partial<SpotlightEntry> = {}): SpotlightEntry => ({
  ...base,
  group: "now",
  rank: n,
  stat_rank: n,
  key: `n${n}`,
  title_ko: `오늘 ${n}`,
  ...over,
});

describe("groups", () => {
  it("a section lists 최근 24시간 then 지속 주목, each under a heading with its count", () => {
    render(<SectionList entries={[sustainedEntry(1), nowEntry(2), nowEntry(1)]} />);
    const now = screen.getByRole("region", { name: /최근 24시간/ });
    const lasting = screen.getByRole("region", { name: /지속 주목/ });
    expect(within(now).getByRole("heading", { level: 2 })).toHaveTextContent("최근 24시간2건");
    expect(within(lasting).getByRole("heading", { level: 2 })).toHaveTextContent("지속 주목1건");
    expect(within(now).getAllByRole("link").map((link) => link.textContent)).toEqual(["오늘 1", "오늘 2"]);
    expect(within(lasting).getByRole("link")).toHaveTextContent("지속 1");
    // the heading order follows the groups
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["최근 24시간2건", "지속 주목1건"]);
  });

  it("says when a group is empty, and reads entries without a group as 24 h", () => {
    const { group: _omitted, ...older } = nowEntry(1);
    render(<SectionList entries={[older as SpotlightEntry]} />);
    expect(within(screen.getByRole("region", { name: /최근 24시간/ })).getByText("오늘 1")).toBeInTheDocument();
    expect(screen.getByText("여러 날 이어진 화제가 없습니다")).toBeInTheDocument();
  });

  it("the overview shows the top three of 24 h and the top two of 지속 주목 per section", () => {
    const sections = emptySections();
    sections.news = [1, 2, 3, 4].map((n) => nowEntry(n)).concat([1, 2, 3].map((n) => sustainedEntry(n)));
    render(<Overview view={viewOf({ sections })} date={null} />);
    const block = screen.getByRole("heading", { level: 2, name: "뉴스" }).closest("section")!;
    expect(within(block).getByRole("heading", { level: 3, name: "최근 24시간" })).toBeInTheDocument();
    expect(within(block).getByRole("heading", { level: 3, name: "지속 주목" })).toBeInTheDocument();
    expect(within(block).getByText("오늘 3")).toBeInTheDocument();
    expect(within(block).queryByText("오늘 4")).not.toBeInTheDocument();
    expect(within(block).getByText("지속 2")).toBeInTheDocument();
    expect(within(block).queryByText("지속 3")).not.toBeInTheDocument();
  });
});

describe("tags, signals and field", () => {
  it("shows Opus's tags, the server's signals and the field chip, without repeating a metric", () => {
    render(<EntryRow entry={{ ...base, tags: ["가격 인하", "첫 공개"], signals: ["보도 14곳", "커뮤니티 확산"], field: "ai", field_label: "AI 모델·에이전트" }} />);
    const reasons = screen.getByRole("list", { name: "주목 이유" });
    expect(within(reasons).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["가격 인하", "첫 공개", "보도 14곳", "커뮤니티 확산"]);
    // the field chip reads "분야 …" to a screen reader
    expect(screen.getByText("AI 모델·에이전트").closest("[data-slot=badge]")).toHaveTextContent("분야 AI 모델·에이전트");
    // the source count is a signal now; the metric chips keep the rest
    const metrics = screen.getByRole("list", { name: "화제 지표" });
    expect(within(metrics).queryByText("보도 14곳")).not.toBeInTheDocument();
    expect(within(metrics).getByText("언급 3")).toBeInTheDocument();
  });

  it("shows nothing extra for entries published before tags", () => {
    render(<EntryRow entry={base} />);
    expect(screen.queryByRole("list", { name: "주목 이유" })).not.toBeInTheDocument();
    expect(screen.queryByText("분야")).not.toBeInTheDocument();
  });

  it("does not repeat the trend or leaderboard chip as a signal", () => {
    render(<EntryRow entry={{ ...base, metrics: { basis: "github_daily", trend_rank: 3, rank: 3 }, signals: ["GitHub 3위", "커뮤니티 확산"] }} />);
    expect(screen.getByText("GitHub 트렌딩 3위")).toBeInTheDocument();
    expect(screen.queryByText("GitHub 3위")).not.toBeInTheDocument();
    expect(screen.getByText("커뮤니티 확산")).toBeInTheDocument();
  });

  it("keeps one leaderboard rank and one HF mark", () => {
    const { rerender } = render(<EntryRow entry={{ ...base, metrics: { basis: "benchmark", site: "LMArena", board: "text", rank: 2 }, signals: ["벤치마크 2위"] }} />);
    expect(screen.getByText("LMArena 2위")).toBeInTheDocument();
    expect(screen.queryByText("벤치마크 2위")).not.toBeInTheDocument();
    rerender(<EntryRow entry={{ ...base, metrics: { basis: "hf_trending", trending: 40 }, signals: ["HF 트렌딩"] }} />);
    expect(screen.getAllByText("HF 트렌딩")).toHaveLength(1);
    // without a trend chip the signal is the only place the fact shows
    rerender(<EntryRow entry={{ ...base, metrics: { source_count: 2 }, signals: ["GitHub 최고 2위"] }} />);
    expect(screen.getByText("GitHub 최고 2위")).toBeInTheDocument();
  });

  it("the overview shows the insight tags", () => {
    const sections = emptySections();
    sections.ai = [nowEntry(1, { tags: ["오픈 웨이트"] })];
    render(<Overview view={viewOf({ sections })} date={null} />);
    expect(screen.getByText("오픈 웨이트")).toBeInTheDocument();
  });
});

describe("filters", () => {
  const ai = { field: "ai", field_label: "AI 모델·에이전트" };
  const display = { field: "display_av", field_label: "디스플레이·영상·오디오" };
  const view = () => {
    const sections = emptySections();
    sections.news = [nowEntry(1, ai), nowEntry(2, display), sustainedEntry(1, ai)];
    sections.product = [nowEntry(1, { ...display, key: "p1", title_ko: "제품 1" })];
    return viewOf({ sections });
  };

  it("parse only well-formed values from the address", () => {
    expect(parseFilters("ai", "sustained")).toEqual({ field: "ai", group: "sustained" });
    expect(parseFilters("AI; drop", "later")).toEqual({ field: null, group: null });
    expect(parseFilters(undefined, undefined)).toEqual({ field: null, group: null });
  });

  it("count the fields present and narrow by field and group", () => {
    const entries = view().sections.news;
    expect(fieldCounts(entries)).toEqual([
      { key: "ai", label: "AI 모델·에이전트", count: 2 },
      { key: "display_av", label: "디스플레이·영상·오디오", count: 1 },
    ]);
    expect(filterEntries(entries, { field: "ai", group: null }).map((e) => e.key)).toEqual(["n1", "s1"]);
    expect(filterEntries(entries, { field: null, group: "sustained" }).map((e) => e.key)).toEqual(["s1"]);
    expect(spotlightHref("news", "2026-11-03", { field: "ai", group: "now" })).toBe("/spotlight?tab=news&date=2026-11-03&field=ai&group=now");
  });

  it("narrow a section tab by field and keep it in the address", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    render(<SpotlightBrowser view={view()} tab="news" date={null} initial={{ field: null, group: null }} />);
    const fields = screen.getByRole("group", { name: "분야 필터" });
    expect(within(fields).getByRole("button", { name: /전체/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(within(fields).getByRole("button", { name: /디스플레이·영상·오디오/ }));
    expect(within(fields).getByRole("button", { name: /디스플레이·영상·오디오/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("오늘 2")).toBeInTheDocument();
    expect(screen.queryByText("오늘 1")).not.toBeInTheDocument();
    expect(screen.queryByText("지속 1")).not.toBeInTheDocument();
    expect(replace).toHaveBeenLastCalledWith(null, "", "/spotlight?tab=news&field=display_av");
    replace.mockRestore();
  });

  it("show one group on the overview and open with the address's filters", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    render(<SpotlightBrowser view={view()} tab="overview" date={null} initial={{ field: "ai", group: null }} />);
    expect(screen.getByText("오늘 1")).toBeInTheDocument();
    expect(screen.queryByText("오늘 2")).not.toBeInTheDocument();
    // a section with nothing in the field says the filter emptied it
    const product = screen.getByRole("heading", { level: 2, name: "제품" }).closest("section")!;
    expect(within(product).getByText("조건에 맞는 항목이 없습니다")).toBeInTheDocument();
    const groups = screen.getByRole("group", { name: "묶음 필터" });
    fireEvent.click(within(groups).getByRole("button", { name: "지속 주목" }));
    expect(within(groups).getByRole("button", { name: "지속 주목" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("지속 1")).toBeInTheDocument();
    expect(screen.queryByText("오늘 1")).not.toBeInTheDocument();
    expect(replace).toHaveBeenLastCalledWith(null, "", "/spotlight?field=ai&group=sustained");
    replace.mockRestore();
  });
});
