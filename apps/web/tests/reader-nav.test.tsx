import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BottomNav } from "@/components/reader/bottom-nav";
import { READER_NAV, isReaderActive } from "@/components/reader/reader-header";
import { RoadmapTabs } from "@/components/reader/roadmap-tabs";

const navigation = vi.hoisted(() => ({ pathname: "/board" }));
vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname }));
// the account menu's logout action is server code
vi.mock("@/components/reader/account-menu", () => ({ AccountMenu: () => null }));

const item = (label: string) => READER_NAV.find((entry) => entry.label === label)!;

describe("reader menu", () => {
  it("starts with the daily briefing and leaves dossiers, collections and questions out", () => {
    expect(READER_NAV.map((entry) => entry.label)).toEqual(["데일리 브리핑", "탐색", "레이더", "투자·제휴", "특허", "로드맵", "보고서"]);
    expect(READER_NAV.some((entry) => ["/dossiers", "/collections", "/ask"].includes(entry.href))).toBe(false);
  });

  it("lights 로드맵 for both of its tabs and 탐색 for home and articles", () => {
    expect(isReaderActive("/roadmap", item("로드맵"))).toBe(true);
    expect(isReaderActive("/board", item("로드맵"))).toBe(true);
    expect(isReaderActive("/boardroom", item("로드맵"))).toBe(false);
    expect(isReaderActive("/", item("탐색"))).toBe(true);
    expect(isReaderActive("/items/4", item("탐색"))).toBe(true);
    expect(isReaderActive("/briefings/2026-10-12", item("데일리 브리핑"))).toBe(true);
    expect(isReaderActive("/", item("데일리 브리핑"))).toBe(false);
  });

  it("lights 보고서 for the list and a report", () => {
    expect(isReaderActive("/reports", item("보고서"))).toBe(true);
    expect(isReaderActive("/reports/12", item("보고서"))).toBe(true);
  });

  it("shows the same seven entries at the bottom on phones", () => {
    render(<BottomNav />);
    const links = within(screen.getByRole("navigation", { name: "하단 메뉴" })).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(READER_NAV.map((entry) => entry.label));
    expect(screen.getByRole("link", { name: "로드맵" })).toHaveAttribute("aria-current", "page");
  });
});

describe("RoadmapTabs", () => {
  it("marks the open tab", () => {
    render(<RoadmapTabs active="board" />);
    expect(screen.getByRole("link", { name: "기회·위협 보드" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "성숙도·로드맵" })).not.toHaveAttribute("aria-current");
  });
});
