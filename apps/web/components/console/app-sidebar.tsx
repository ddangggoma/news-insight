"use client";

import { Activity, BellRing, ClipboardCheck, Lightbulb, Gauge, History, GitMerge, Layers, Inbox, LayoutDashboard, LayoutGrid, Library, Newspaper, Radar, Rss, TrendingUp } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

const NAV = [
  { label: "개요", items: [
    { href: "/console", title: "대시보드", icon: LayoutDashboard },
    { href: "/console/alerts", title: "운영 알림", icon: BellRing },
    { href: "/console/briefing", title: "데일리 브리핑", icon: Newspaper },
    { href: "/console/digests", title: "다이제스트 이력", icon: History },
  ] },
  { label: "수집", items: [
    { href: "/console/sources", title: "소스", icon: Rss },
    { href: "/console/runs", title: "수집 현황", icon: Activity },
    { href: "/console/dlq", title: "DLQ", icon: Inbox },
    { href: "/console/quality", title: "소스 품질", icon: Gauge },
  ] },
  { label: "인텔리전스", items: [
    { href: "/console/cards", title: "카드 뉴스", icon: LayoutGrid },
    { href: "/console/stories", title: "이슈 묶음", icon: Layers },
    { href: "/console/signals", title: "교차 신호", icon: GitMerge },
    { href: "/console/items", title: "수집 항목", icon: Library },
    { href: "/console/trends", title: "지표 상승", icon: TrendingUp },
    { href: "/console/review", title: "관련성 검토", icon: ClipboardCheck },
    { href: "/console/topic-candidates", title: "미분류 신호", icon: Lightbulb },
  ] },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/console" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar() {
  const pathname = usePathname();
  const { isMobile, setOpenMobile } = useSidebar();
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
        {NAV.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarMenu>
              {group.items.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton asChild isActive={isActive(pathname, item.href)} tooltip={item.title}>
                    <Link href={item.href} onClick={() => isMobile && setOpenMobile(false)}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="px-4 pb-4 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
        매일 05:00 KST 발행
      </SidebarFooter>
    </Sidebar>
  );
}
