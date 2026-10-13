"use client";

import { Compass, FileSearch, FileText, Handshake, Map as MapIcon, Radar, ScrollText, Search } from "lucide-react";
import { AppLink as Link } from "@/components/app-link";
import { usePathname, useSearchParams } from "next/navigation";

import { ThemeToggle } from "@/components/console/theme-toggle";
import { type AccountSummary, AccountMenu } from "@/components/reader/account-menu";
import { cn } from "@/lib/utils";

// Reader menu (2026-10-12): the daily briefing first; the opportunity/threat board and the
// roadmap share one entry with tabs (components/reader/roadmap-tabs.tsx). Dossiers, collections
// and questions left the menu; their pages still open from a direct link. Trend reports on request
// (plan 17 R1) joined it on 2026-10-13.
export const READER_NAV = [
  { href: "/briefings", label: "데일리 브리핑", icon: FileText, match: ["/briefings"] },
  { href: "/", label: "탐색", icon: Compass, match: ["/items"] },
  { href: "/radar", label: "레이더", icon: Radar, match: ["/radar"] },
  { href: "/deals", label: "투자·제휴", icon: Handshake, match: ["/deals"] },
  { href: "/patents", label: "특허", icon: ScrollText, match: ["/patents"] },
  { href: "/roadmap", label: "로드맵", icon: MapIcon, match: ["/roadmap", "/board"] },
  { href: "/reports", label: "동향 보고서 작성", icon: FileSearch, match: ["/reports"] },
] as const;

export function isReaderActive(pathname: string, item: (typeof READER_NAV)[number]): boolean {
  if (item.href === "/" && pathname === "/") return true;
  return item.match.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function ReaderHeader({ user }: { user: AccountSummary }) {
  const pathname = usePathname();
  const query = useSearchParams().get("q") ?? "";
  return (
    <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 md:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold whitespace-nowrap">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Radar className="size-4" aria-hidden />
          </span>
          DX 인텔리전스
        </Link>
        <nav aria-label="주요 메뉴" className="hidden items-center gap-1 md:flex">
          {READER_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isReaderActive(pathname, item) ? "page" : undefined}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm whitespace-nowrap text-muted-foreground hover:bg-muted hover:text-foreground",
                isReaderActive(pathname, item) && "bg-muted font-semibold text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <form
          action="/"
          role="search"
          className="order-last flex w-full items-center gap-2 rounded-lg border bg-muted/60 px-3 focus-within:border-primary md:order-none md:ml-auto md:w-80"
        >
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            key={query}
            name="q"
            type="search"
            defaultValue={query}
            placeholder="기사·키워드 검색"
            aria-label="기사·키워드 검색"
            className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </form>
        <div className="ml-auto flex items-center gap-1 md:ml-0">
          <ThemeToggle />
          <AccountMenu user={user} />
        </div>
      </div>
    </header>
  );
}
