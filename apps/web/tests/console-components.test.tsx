import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OutcomeBadge, StageBadge, StatusBadge } from "@/components/console/badges";
import { type Column, DataTable } from "@/components/console/data-table";
import { DigestView } from "@/components/console/digest-view";
import { PaginationBar } from "@/components/console/pagination-bar";
import { StatCard } from "@/components/console/stat-card";
import { isActive } from "@/components/console/app-sidebar";
import type { DigestOut } from "@/lib/types";

const DIGEST: DigestOut = {
  digest_date: "2026-10-04",
  version: 1,
  status: "published",
  model: "claude-opus",
  generated_at: "2026-10-03T20:00:00Z",
  window_start: "2026-10-02T15:00:00Z",
  window_end: "2026-10-03T15:00:00Z",
  item_count: 2,
  cost_usd: 0.5,
  error: null,
  content: {
    headline: "온디바이스 AI 경쟁 가속",
    overview: "개요 문장",
    tracks: [
      {
        track: "news",
        summary: "뉴스 요약",
        categories: [
          { category: "independent_media", headline: "주요 보도", points: [{ text: "Galaxy 출시", item_ids: [1] }] },
        ],
      },
    ],
    insights: [{ title: "가격 압력", body: "본문", item_ids: [1, 2] }],
  },
  items: [
    { id: 1, title: "Galaxy S30", url: "https://example.com/1", source_name: "The Verge", track: "news" },
    { id: 2, title: "OLED", url: "https://example.com/2", source_name: "ETNews", track: "news" },
  ],
};

describe("console components", () => {
  it("renders Korean status labels", () => {
    render(
      <div>
        <StatusBadge status="paused" />
        <StageBadge stage="unverified" />
        <OutcomeBadge outcome="dead_lettered" />
      </div>,
    );
    expect(screen.getByText("일시정지")).toBeInTheDocument();
    expect(screen.getByText("미검증")).toBeInTheDocument();
    expect(screen.getByText("DLQ")).toBeInTheDocument();
  });

  it("renders a stat card", () => {
    render(<StatCard title="활성 소스" value="12" hint="목표 260" />);
    expect(screen.getByText("활성 소스")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("renders rows or an empty state", () => {
    const columns: Column<{ id: number; name: string }>[] = [{ key: "name", header: "이름", cell: (row) => row.name }];
    const { rerender } = render(<DataTable columns={columns} rows={[{ id: 1, name: "alpha" }]} rowKey={(r) => r.id} emptyTitle="없음" />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
    rerender(<DataTable columns={columns} rows={[]} rowKey={(r) => r.id} emptyTitle="결과가 없습니다" />);
    expect(screen.getByText("결과가 없습니다")).toBeInTheDocument();
  });

  it("builds pagination links that keep filters", () => {
    render(<PaginationBar pathname="/console/sources" params={{ track: "oss" }} page={2} size={50} total={120} />);
    expect(screen.getByRole("link", { name: "이전" })).toHaveAttribute("href", "/console/sources?track=oss");
    expect(screen.getByRole("link", { name: "다음" })).toHaveAttribute("href", "/console/sources?track=oss&page=3");
    expect(screen.getByText(/총 120건/)).toBeInTheDocument();
  });

  it("renders a digest with evidence links", () => {
    render(<DigestView digest={DIGEST} />);
    expect(screen.getByRole("heading", { name: "온디바이스 AI 경쟁 가속" })).toBeInTheDocument();
    const insight = screen.getByText("가격 압력").closest("article");
    expect(insight).not.toBeNull();
    const links = within(insight as HTMLElement).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["https://example.com/1", "https://example.com/2"]);
    expect(screen.getByText("Galaxy 출시")).toBeInTheDocument();
  });

  it("marks the active menu item", () => {
    expect(isActive("/console", "/console")).toBe(true);
    expect(isActive("/console/sources", "/console")).toBe(false);
    expect(isActive("/console/sources/etnews", "/console/sources")).toBe(true);
  });
});
