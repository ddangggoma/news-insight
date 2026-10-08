"use client";

import { Activity, BellRing, ChevronDown, Network, ClipboardCheck, Cpu, Gauge, GitMerge, History, Inbox, Layers, LayoutDashboard, LayoutGrid, Library, Lightbulb, Newspaper, Radar, Rss, Star, TrendingUp, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

// Six groups instead of four long ones (2026-10-08). `folded` groups start closed unless they
// hold the current page; the reader's choice is remembered in this browser.
const NAV: { label: string; folded?: boolean; items: { href: string; title: string; icon: typeof Rss }[] }[] = [
  { label: "개요", items: [
    { href: "/console", title: "대시보드", icon: LayoutDashboard },
    { href: "/console/alerts", title: "운영 알림", icon: BellRing },
  ] },
  { label: "브리핑", items: [
    { href: "/console/briefing", title: "데일리 브리핑", icon: Newspaper },
    { href: "/console/digests", title: "다이제스트 이력", icon: History },
    { href: "/console/watchlist", title: "관심 목록", icon: Star },
  ] },
  { label: "분석", items: [
    { href: "/console/cards", title: "카드 뉴스", icon: LayoutGrid },
    { href: "/console/stories", title: "이슈 묶음", icon: Layers },
    { href: "/console/signals", title: "교차 신호", icon: GitMerge },
    { href: "/console/trends", title: "지표 상승", icon: TrendingUp },
    { href: "/console/items", title: "수집 항목", icon: Library },
  ] },
  { label: "수집", items: [
    { href: "/console/sources", title: "소스", icon: Rss },
    { href: "/console/runs", title: "수집 현황", icon: Activity },
    { href: "/console/quality", title: "소스 품질", icon: Gauge },
    { href: "/console/dlq", title: "DLQ", icon: Inbox },
  ] },
  { label: "분류 관리", folded: true, items: [
    { href: "/console/taxonomy", title: "분류 체계", icon: Network },
    { href: "/console/review", title: "관련성 검토", icon: ClipboardCheck },
    { href: "/console/topic-candidates", title: "미분류 신호", icon: Lightbulb },
    { href: "/console/technologies", title: "기술 레지스트리", icon: Cpu },
  ] },
  { label: "관리", folded: true, items: [
    { href: "/console/users", title: "사용자", icon: Users },
  ] },
];
const FOLD_KEY = "console-sidebar-folds";

function readFolds(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(FOLD_KEY) ?? "{}") as Record<string, boolean>;
  } catch {
    return {};
  }
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/console" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar({ pendingUsers = 0 }: { pendingUsers?: number }) {
  const pathname = usePathname();
  const { isMobile, setOpenMobile, state } = useSidebar();
  const [folds, setFolds] = useState<Record<string, boolean>>({});
  useEffect(() => setFolds(readFolds()), []);
  const toggle = (label: string, open: boolean) => {
    const next = { ...folds, [label]: open };
    setFolds(next);
    try {
      localStorage.setItem(FOLD_KEY, JSON.stringify(next));
    } catch {
      // private mode: the choice lasts for this page only
    }
  };
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link href="/console" className="flex items-center gap-2 px-2 py-1.5 font-semibold">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Radar className="size-4" />
          </span>
          <span className="truncate group-data-[collapsible=icon]:hidden">DX Intelligence</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        {NAV.map((group) => {
          const current = group.items.some((item) => isActive(pathname, item.href));
          const badge = group.items.some((item) => item.href === "/console/users") && pendingUsers > 0;
          // icon-only sidebar: every icon stays reachable; the group with the current page stays open
          const open = state === "collapsed" || current || !(folds[group.label] ?? group.folded ?? false);
          return (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel asChild>
                <button type="button" aria-expanded={open} onClick={() => toggle(group.label, open)} className="flex w-full items-center justify-between">
                  <span>
                    {group.label}
                    {!open && badge ? <span className="ml-1.5 rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground">{pendingUsers}</span> : null}
                  </span>
                  <ChevronDown className={`size-3.5 transition-transform ${open ? "" : "-rotate-90"}`} aria-hidden />
                </button>
              </SidebarGroupLabel>
              {open ? (
            <SidebarMenu>
              {group.items.map((item) => (
                <SidebarMenuItem key={item.href}>
                  {/* no prefetch: each prefetch is a full session check in proxy.ts (plan 14), ~20 per page */}
                  <SidebarMenuButton asChild isActive={isActive(pathname, item.href)} tooltip={item.title}>
                    <Link href={item.href} prefetch={false} onClick={() => isMobile && setOpenMobile(false)}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                  {item.href === "/console/users" && pendingUsers > 0 ? (
                    <SidebarMenuBadge aria-label={`승인 대기 ${pendingUsers}건`}>{pendingUsers}</SidebarMenuBadge>
                  ) : null}
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
              ) : null}
            </SidebarGroup>
          );
        })}
      </SidebarContent>
      <SidebarFooter className="px-4 pb-4 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
        매일 05:00 KST 발행
      </SidebarFooter>
    </Sidebar>
  );
}
