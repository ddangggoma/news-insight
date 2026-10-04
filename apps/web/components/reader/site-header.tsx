import { BookMarked, CalendarDays, Newspaper, Rss, Search } from "lucide-react";
import Link from "next/link";

import { ThemeToggle } from "@/components/console/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const NAV = [
  { href: "/", label: "오늘", icon: Newspaper },
  { href: "/archive", label: "아카이브", icon: CalendarDays },
  { href: "/library", label: "내 서재", icon: BookMarked },
] as const;

export function SiteHeader({ query }: { query?: string }) {
  return (
    <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-xs font-bold text-primary-foreground">DI</span>
          <span className="hidden sm:inline">Daily IT Intelligence</span>
        </Link>
        <nav aria-label="주 메뉴" className="flex items-center gap-0.5">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Button key={href} asChild variant="ghost" size="sm" className="px-2">
              <Link href={href}>
                <Icon className="size-4" aria-hidden />
                <span className="hidden md:inline">{label}</span>
              </Link>
            </Button>
          ))}
        </nav>
        <Button asChild variant="ghost" size="icon" className="ml-auto sm:hidden" aria-label="검색">
          <Link href="/search">
            <Search className="size-4" />
          </Link>
        </Button>
        <form action="/search" role="search" className="ml-auto hidden max-w-sm min-w-0 flex-1 items-center sm:flex">
          <label htmlFor="site-search" className="sr-only">
            기사 검색
          </label>
          <div className="relative w-full">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input id="site-search" name="q" type="search" defaultValue={query} placeholder="원문·한국어 검색" className="h-9 pl-8" />
          </div>
        </form>
        <Button asChild variant="ghost" size="icon" aria-label="RSS 구독">
          <a href="/rss.xml">
            <Rss className="size-4" />
          </a>
        </Button>
        <ThemeToggle />
      </div>
    </header>
  );
}
