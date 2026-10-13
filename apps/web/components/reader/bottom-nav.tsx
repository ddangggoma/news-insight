"use client";

import { AppLink as Link } from "@/components/app-link";
import { usePathname } from "next/navigation";

import { READER_NAV, isReaderActive } from "@/components/reader/reader-header";
import { cn } from "@/lib/utils";

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="하단 메뉴"
      className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-7 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {READER_NAV.map((item) => {
        const active = isReaderActive(pathname, item);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex flex-col items-center gap-0.5 px-0.5 py-2 text-center text-[11px] leading-tight text-muted-foreground",
              active && "font-semibold text-primary",
            )}
          >
            <item.icon className="size-5" aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
