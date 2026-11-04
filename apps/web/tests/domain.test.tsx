import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { CompanyTable, type RankRow } from "@/components/reader/domain/company-table";
import { DomainPage } from "@/components/reader/domain/domain-view";
import { DomainTabs, HeatmapTable, InsightBlock, PeriodSelect } from "@/components/reader/domain/parts";
import {
  type Doc,
  type DomainState,
  type DomainView,
  type Span,
  changeText,
  domainHref,
  domainQuery,
  heatLevel,
  kpiStats,
  parseDomainState,
  tabHref,
} from "@/lib/domain-types";

beforeAll(() => {
  // Recharts' ResponsiveContainer measures its parent; jsdom has no ResizeObserver
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

const state = (over: Partial<DomainState> = {}): DomainState => ({
  tab: "overview",
  period: "month",
  field: null,
  company: null,
  org: null,
  kind: "company",
  page: 1,
  view: "chart",
  ...over,
});

const weeks: Span[] = [
  { start: "2026-10-13", end: "2026-10-19" },
  { start: "2026-10-20", end: "2026-10-26" },
  { start: "2026-10-27", end: "2026-11-02" },
];

const doc = (over: Partial<Doc> = {}): Doc => ({
  id: 41,
  url: "https://arxiv.org/abs/2610.1",
  title: "On-device LLM quantization",
  title_ko: "온디바이스 LLM 양자화",
  summary: "메모리를 60% 줄였다.",
  source_name: "arXiv",
  occurred_at: "2026-11-02T03:00:00Z",
  field: "ai",
  field_label: "AI",
  companies: [{ key: "samsung", label: "삼성전자", relation: "self", kind: "company", watched: true }],
  watched: true,
  score: 23.4,
  venue: "NeurIPS",
  orgs: ["KAIST"],
  cited_by: 4,
  mentions: 2,
  upvotes: 12,
  ...over,
});

const viewOf = (over: Partial<DomainView> = {}): DomainView => ({
  kind: "research",
  tab: "overview",
  period: "month",
  as_of: "2026-11-03",
  window: { start: "2026-10-05", end: "2026-11-03" },
  previous: { start: "2026-09-05", end: "2026-10-04" },
  field: null,
  company: null,
  org: null,
  field_options: [
    { key: "ai", label: "AI" },
    { key: "semis", label: "반도체" },
  ],
  coverage: null,
  ...over,
});

const overview = {
  kpis: {
    count: 120,
    previous: 100,
    change: 0.2,
    rising_field: { key: "ai", label: "AI", count: 40, mean: 20, ratio: 2, z: 2.5 },
    company_share: 0.25,
    company_docs: 30,
    watched_count: 6,
    watched_previous: 3,
  },
  heatmap: {
    weeks,
    rows: [
      { key: "ai", label: "AI", counts: [2, 0, 10] },
      { key: "semis", label: "반도체", counts: [1, 1, 0] },
    ],
    max: 10,
  },
  risers: [{ key: "ai", label: "AI", count: 40, mean: 20, ratio: 2, z: 2.5 }],
  insight: null,
};

describe("domain state and links", () => {
  it("reads the address with defaults and drops research-only params on patents", () => {
    expect(parseDomainState("research", { tab: "companies", period: "week", kind: "org", org: "KAIST", page: "3" })).toMatchObject({
      tab: "companies",
      period: "week",
      kind: "org",
      org: "KAIST",
      page: 3,
    });
    expect(parseDomainState("patent", { tab: "nope", period: "year", org: "KAIST", kind: "org" })).toMatchObject({ tab: "overview", period: "month", org: null, kind: "company" });
  });

  it("writes only what differs from the defaults", () => {
    expect(domainHref("research", state())).toBe("/research");
    expect(domainHref("patent", state({ tab: "trends", period: "quarter", view: "table" }))).toBe("/patents?tab=trends&period=quarter&view=table");
    expect(domainHref("research", state({ tab: "companies", kind: "org", org: "Seoul National University" }))).toBe("/research?tab=companies&kind=org&org=Seoul+National+University");
  });

  it("keeps the period and field across tabs but not the selection or page", () => {
    const current = state({ tab: "documents", period: "week", field: "ai", company: "samsung", page: 4 });
    expect(tabHref("research", current, "trends")).toBe("/research?tab=trends&period=week&field=ai");
  });

  it("asks the API only for what the tab reads", () => {
    expect(domainQuery("research", state({ field: "ai", company: "samsung" }))).toEqual({ tab: "overview", period: "month" });
    expect(domainQuery("research", state({ tab: "companies", kind: "org", org: "KAIST" }))).toEqual({ tab: "companies", period: "month", org: "KAIST", kind: "org" });
    expect(domainQuery("patent", state({ tab: "documents", page: 2, company: "lg" }))).toEqual({ tab: "documents", period: "month", company: "lg", page: 2 });
  });

  it("writes changes as arrows, 새로 from nothing", () => {
    expect([changeText(0.25, 5, 4), changeText(-0.1, 9, 10), changeText(0, 3, 3), changeText(null, 2, 0), changeText(null, 0, 0)]).toEqual(["▲25%", "▼10%", "±0%", "새로", "–"]);
    expect([heatLevel(0, 10), heatLevel(1, 10), heatLevel(10, 10)]).toEqual([0, 10, 88]);
  });
});

describe("tabs and period", () => {
  it("marks the open tab and links the others with the period kept", () => {
    render(<DomainTabs domain="research" state={state({ tab: "fields", period: "quarter", field: "semis" })} />);
    const nav = screen.getByRole("navigation", { name: "연구 보기" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["개요", "기술분야별", "기업·기관별", "추이", "주목 문헌"]);
    expect(within(nav).getByRole("link", { name: "기술분야별" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "추이" })).toHaveAttribute("href", "/research?tab=trends&period=quarter&field=semis");
    expect(within(nav).getByRole("link", { name: "개요" })).not.toHaveAttribute("aria-current");
  });

  it("marks the period and keeps the tab when it changes", () => {
    render(<PeriodSelect domain="patent" state={state({ tab: "companies", page: 3 })} />);
    const nav = screen.getByRole("navigation", { name: "기간" });
    expect(within(nav).getByRole("link", { name: "1개월" })).toHaveAttribute("aria-current", "true");
    expect(within(nav).getByRole("link", { name: "1주" })).toHaveAttribute("href", "/patents?tab=companies&period=week");
  });
});

describe("overview", () => {
  it("shows the four tiles, the heatmap as a table and the risers", () => {
    render(<DomainPage view={viewOf({ overview })} state={state()} />);
    expect(screen.getByRole("heading", { level: 1, name: "연구" })).toBeInTheDocument();
    expect(screen.getByText("이번 기간 논문")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("기업 저자 비중")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText("관심 기업 논문")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "급증 분야 Top 5" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    // research shows no data-range note unless the API sends one
    expect(screen.queryByRole("note", { name: "데이터 범위" })).toBeNull();
  });

  it("builds tiles with the change against the previous window", () => {
    const stats = kpiStats(viewOf(), overview.kpis);
    expect(stats.map((s) => s.label)).toEqual(["이번 기간 논문", "급증 분야", "기업 저자 비중", "관심 기업 논문"]);
    expect(stats[0].note).toContain("▲20%");
    expect(stats[1].value).toBe("AI");
    expect(stats[3].note).toContain("▲100%");
  });

  it("draws heat cells with readable labels and links each field to its tab", () => {
    render(<HeatmapTable heatmap={overview.heatmap} href={(field) => `/research?tab=fields&field=${field}`} />);
    const table = screen.getByRole("table");
    expect(within(table).getByText(/기술분야별 주간 문헌 수/)).toBeInTheDocument();
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["분야", "10/13", "10/20", "10/27", "합계"]);
    const cell = within(table).getByLabelText("AI 10/27–11/2 10건");
    expect(cell).toHaveAttribute("data-level", "88");
    expect(within(table).getByLabelText("AI 10/20–10/26 0건")).toHaveAttribute("data-level", "0");
    expect(within(table).getByRole("rowheader", { name: "반도체" })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "AI" })).toHaveAttribute("href", "/research?tab=fields&field=ai");
  });

  it("says when there is nothing to map", () => {
    render(<HeatmapTable heatmap={{ weeks, rows: [{ key: "ai", label: "AI", counts: [0, 0, 0] }], max: 0 }} href={() => "#"} />);
    expect(screen.getByText("최근 12주 동안 집계된 문헌이 없습니다.")).toBeInTheDocument();
  });
});

describe("insight", () => {
  it("links each sentence to the documents behind it", () => {
    render(
      <InsightBlock
        today="2026-11-04"
        insight={{
          date: "2026-11-02",
          sentences: [
            { text: "AI 논문이 두 배로 늘었습니다.", doc_ids: [41, 42] },
            { text: "삼성전자 논문이 처음 나왔습니다.", doc_ids: [43] },
          ],
        }}
      />,
    );
    expect(screen.getByText("AI 논문이 두 배로 늘었습니다.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "근거 문헌 1" })).toHaveAttribute("href", "/items/41");
    expect(screen.getByRole("link", { name: "근거 문헌 3" })).toHaveAttribute("href", "/items/43");
    expect(screen.getByText(/2026\.11\.02 작성 \(가장 최근 발행본\)/)).toBeInTheDocument();
  });

  it("says today instead of the date when the insight is today's", () => {
    render(<InsightBlock today="2026-11-04" insight={{ date: "2026-11-04", sentences: [{ text: "오늘 문장.", doc_ids: [] }] }} />);
    expect(screen.getByText("오늘 작성")).toBeInTheDocument();
    expect(screen.queryByText(/2026\.11\.04/)).toBeNull();
    expect(screen.queryByText(/가장 최근 발행본/)).toBeNull();
  });

  it("uses today's KST date when none is given", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-03T16:30:00Z")); // 01:30 KST on the 4th
    try {
      render(<InsightBlock insight={{ date: "2026-11-04", sentences: [{ text: "자정 뒤.", doc_ids: [] }] }} />);
      expect(screen.getByText("오늘 작성")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a quiet placeholder until the first insight is written", () => {
    render(<InsightBlock insight={null} />);
    expect(screen.getByText("인사이트는 매일 05시 브리핑 뒤에 작성됩니다.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("leaves a field without a line quiet", () => {
    const { container } = render(<InsightBlock insight={null} title="반도체 인사이트" compact />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("fields", () => {
  const fieldsView = viewOf({
    tab: "fields",
    field: "semis",
    fields: {
      items: [
        { key: "ai", label: "AI", count: 40, previous: 20, change: 1 },
        { key: "semis", label: "반도체", count: 0, previous: 2, change: -1 },
      ],
      other: { key: "other", label: "미분류", count: 3, previous: 0, change: null },
      selected: "semis",
      buckets: weeks,
      detail: {
        key: "semis",
        label: "반도체",
        count: 0,
        previous: 2,
        change: -1,
        themes: [],
        series: [0, 2, 0],
        companies: [],
        orgs: [],
        documents: [],
        insight: null,
      },
    },
  });

  it("marks the chosen field chip and links the others", () => {
    render(<DomainPage view={fieldsView} state={state({ tab: "fields", field: "semis" })} />);
    const chips = screen.getByRole("navigation", { name: "기술분야" });
    expect(within(chips).getByRole("link", { name: /반도체/ })).toHaveAttribute("aria-current", "true");
    expect(within(chips).getByRole("link", { name: /^AI/ })).toHaveAttribute("href", "/research?tab=fields&field=ai");
    expect(within(chips).getByRole("link", { name: /미분류/ })).toHaveAttribute("href", "/research?tab=fields&field=other");
    expect(screen.getByRole("heading", { level: 2, name: "반도체" })).toBeInTheDocument();
    expect(screen.getByText("이 기간 반도체 분야 논문이 없습니다.")).toBeInTheDocument();
  });

  it("shows the field's one-liner with its documents and date", () => {
    const detail = { ...fieldsView.fields!.detail, insight: { date: "2026-11-02", sentences: [{ text: "반도체 특허가 줄었다.", doc_ids: [7], key: "semis" }] } };
    render(<DomainPage view={{ ...fieldsView, fields: { ...fieldsView.fields!, detail } }} state={state({ tab: "fields", field: "semis" })} />);
    const block = screen.getByRole("region", { name: "반도체 인사이트" });
    expect(within(block).getByText("반도체 특허가 줄었다.")).toBeInTheDocument();
    expect(within(block).getByRole("link", { name: "근거 문헌 1" })).toHaveAttribute("href", "/items/7");
    expect(within(block).getByText(/2026\.11\.02 작성 \(가장 최근 발행본\)/)).toBeInTheDocument();
  });

  it("says when a field has no documents at all", () => {
    const empty = { ...fieldsView.fields!, detail: { ...fieldsView.fields!.detail, series: [0, 0, 0], previous: 0, change: null } };
    render(<DomainPage view={{ ...fieldsView, fields: empty }} state={state({ tab: "fields", field: "semis" })} />);
    expect(screen.getByText(/최근 3개 기간 동안 반도체 분야 논문이 없습니다/)).toBeInTheDocument();
  });
});

describe("company table", () => {
  const rows: RankRow[] = [
    { key: "lg", label: "LG전자", entity: "company", relation: "competitor", kind: "company", org_type: null, watched: true, count: 3, previous: 1, change: 2, top_fields: [{ key: "ai", label: "AI", count: 2, previous: 1, change: 1 }], rank: 1, href: "/patents?tab=companies&company=lg", selected: false },
    { key: "sony", label: "소니", entity: "company", relation: "peer", kind: "company", org_type: null, watched: false, count: 8, previous: 8, change: 0, top_fields: [], rank: 2, href: "/patents?tab=companies&company=sony", selected: true },
  ];

  it("sorts by count, marks watched companies and links each name to its detail", () => {
    render(<CompanyTable rows={rows} label="출원 기업 순위" emptyText="없음" />);
    const table = screen.getByRole("table", { name: "출원 기업 순위" });
    const names = () => within(table).getAllByRole("link").map((a) => a.textContent);
    expect(names()).toEqual(["LG전자", "소니"]);
    fireEvent.click(within(table).getByRole("button", { name: /문헌 수/ }));
    expect(names()).toEqual(["소니", "LG전자"]);
    expect(within(table).getByRole("columnheader", { name: /문헌 수/ })).toHaveAttribute("aria-sort", "descending");
    expect(within(table).getByTitle("관심 기업 (경쟁사)")).toHaveTextContent("관심·경쟁사");
    expect(within(table).getByRole("link", { name: "소니" })).toHaveAttribute("aria-current", "true");
    expect(within(table).getByText("▲200%")).toBeInTheDocument();
    expect(within(table).getByText("AI 2")).toBeInTheDocument();
  });

  it("toggles companies and institutions on the research ranking", () => {
    const view = viewOf({
      tab: "companies",
      companies: { kind: "org", ranking: [], watch: { buckets: weeks, total: 2, companies: [] }, detail: null },
    });
    render(<DomainPage view={view} state={state({ tab: "companies", kind: "org" })} />);
    const toggle = screen.getByRole("navigation", { name: "기관 구분" });
    expect(within(toggle).getByRole("link", { name: "대학·연구기관" })).toHaveAttribute("aria-current", "true");
    expect(within(toggle).getByRole("link", { name: "기업" })).toHaveAttribute("href", "/research?tab=companies");
    expect(screen.getByText(/이 기간 대학·연구기관이 확인된 논문이 없습니다/)).toBeInTheDocument();
    expect(screen.getByText(/이 기간 관심 기업\(자사·경쟁사\) 논문이 없습니다/)).toBeInTheDocument();
  });

  it("opens the selected company's detail with its fields, documents and recent list", () => {
    const view = viewOf({
      kind: "patent",
      tab: "companies",
      company: "lg",
      coverage: { news: 5, eps: 2, ops: 0, note: "지식재산 뉴스·EPO 공보 파일럿 기준(공보 수집은 EPO OPS 키 등록 후)" },
      companies: {
        kind: "company",
        ranking: [],
        watch: { buckets: weeks, total: 1, companies: [] },
        detail: {
          key: "lg",
          label: "LG전자",
          entity: "company",
          relation: "competitor",
          org_type: null,
          watched: true,
          count: 3,
          previous: 1,
          change: 2,
          fields: [{ key: "display_av", label: "디스플레이·AV", count: 3, previous: 1, change: 2 }],
          series: [0, 1, 3],
          top_documents: [doc({ id: 7, title_ko: "폴더블 힌지 특허", publication_number: "EP4815726", office: "EP", press: 3, patent_source: "eps" })],
          documents: [doc({ id: 8, title_ko: "롤러블 패널 특허" })],
        },
      },
    });
    render(<DomainPage view={view} state={state({ tab: "companies", company: "lg" })} />);
    expect(screen.getByRole("heading", { level: 2, name: "LG전자" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "디스플레이·AV" })).toHaveAttribute("href", "/patents?tab=fields&field=display_av");
    expect(screen.getByRole("link", { name: "폴더블 힌지 특허" })).toHaveAttribute("href", "/items/7");
    expect(screen.getByText("EP4815726 · EP")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "최근 특허" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "선택 해제 ✕" })).toHaveAttribute("href", "/patents?tab=companies");
  });
});

describe("patents", () => {
  it("states the data range with the window's source counts", () => {
    const view = viewOf({ kind: "patent", coverage: { news: 12, eps: 4, ops: 0, note: "지식재산 뉴스·EPO 공보 파일럿 기준(공보 수집은 EPO OPS 키 등록 후)" }, overview });
    render(<DomainPage view={view} state={state()} />);
    expect(screen.getByRole("heading", { level: 1, name: "특허" })).toBeInTheDocument();
    const note = screen.getByRole("note", { name: "데이터 범위" });
    expect(note).toHaveTextContent("지식재산 뉴스·EPO 공보 파일럿 기준(공보 수집은 EPO OPS 키 등록 후)");
    expect(note).toHaveTextContent("지식재산 뉴스 12건, EPO 공보 4건, EPO OPS 0건");
    expect(screen.getByText("기업 출원 비중")).toBeInTheDocument();
  });

  it("keeps the pilot note when the API sends no coverage block", () => {
    render(<DomainPage view={viewOf({ kind: "patent", overview })} state={state()} />);
    expect(screen.getByRole("note", { name: "데이터 범위" })).toHaveTextContent("공보 수집은 EPO OPS 키 등록 후");
  });
});

describe("trends and documents", () => {
  const trends = {
    buckets: weeks,
    history: 2,
    fields: [
      { key: "ai", label: "AI", counts: [2, 3, 12], current: 12, mean: 2.5, z: 4.2, flag: "rise" as const },
      { key: "rest", label: "기타", counts: [1, 1, 1], current: 1, mean: 1, z: 0, flag: null },
    ],
    regions_axis: "office" as const,
    regions: [],
    flags: [{ axis: "field" as const, key: "ai", label: "AI", flag: "rise" as const, z: 4.2, current: 12, mean: 2.5 }],
  };

  it("lists the flags and shows the series as a table on request", () => {
    render(<DomainPage view={viewOf({ kind: "patent", tab: "trends", trends })} state={state({ tab: "trends", view: "table" })} />);
    expect(screen.getByText("▲ 급증 AI")).toBeInTheDocument();
    const toggle = screen.getByRole("navigation", { name: "보기 방식" });
    expect(within(toggle).getByRole("link", { name: "표" })).toHaveAttribute("aria-current", "true");
    expect(within(toggle).getByRole("link", { name: "차트" })).toHaveAttribute("href", "/patents?tab=trends");
    const table = screen.getByRole("table", { name: "기술분야별 기간별 문헌 수" });
    expect(within(table).getByRole("rowheader", { name: "AI" })).toBeInTheDocument();
    expect(within(table).getByText("▲ 급증")).toBeInTheDocument();
    expect(screen.getByText("공개국이 확인된 특허가 아직 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "공개국별 추이" })).toBeInTheDocument();
  });

  it("pages the documents with their score signals and a removable company filter", () => {
    const view = viewOf({ tab: "documents", company: "samsung", documents: { page: 2, size: 20, total: 45, items: [doc()] } });
    render(<DomainPage view={view} state={state({ tab: "documents", company: "samsung", page: 2 })} />);
    expect(screen.getByText(/45건 중 21–40/)).toBeInTheDocument();
    expect(screen.getByText("화제 점수")).toBeInTheDocument();
    expect(screen.getByText("23.4")).toBeInTheDocument();
    expect(screen.getByText("HF 추천")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "삼성전자 ✕" })).toHaveAttribute("href", "/research?tab=documents");
    const pager = screen.getByRole("navigation", { name: "페이지" });
    expect(within(pager).getByRole("link", { name: "다음 →" })).toHaveAttribute("href", "/research?tab=documents&company=samsung&page=3");
    expect(within(pager).getByRole("link", { name: "← 이전" })).toHaveAttribute("href", "/research?tab=documents&company=samsung");
    expect(screen.getByRole("link", { name: "전체" })).toHaveAttribute("aria-current", "true");
  });
});
