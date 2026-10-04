"use client";

import { Radar, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { ThemeToggle } from "@/components/console/theme-toggle";
import { cn } from "@/lib/utils";

export const READER_NAV = [
  { href: "/", label: "탐색" },
  { href: "/radar", label: "레이더" },
  { href: "/digests", label: "다이제스트" },
] as const;

export function isReaderActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" || pathname.startsWith("/items") : pathname.startsWith(href);
}

export function ReaderHeader() {
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
              aria-current={isReaderActive(pathname, item.href) ? "page" : undefined}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
                isReaderActive(pathname, item.href) && "bg-muted font-semibold text-foreground",
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
        <div className="ml-auto md:ml-0">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
