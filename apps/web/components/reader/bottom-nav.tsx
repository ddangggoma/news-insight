"use client";

import { Compass, Newspaper, Radar } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { isReaderActive } from "@/components/reader/reader-header";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/", label: "탐색", icon: Compass },
  { href: "/radar", label: "레이더", icon: Radar },
  { href: "/digests", label: "다이제스트", icon: Newspaper },
];

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="하단 메뉴"
      className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-3 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {ITEMS.map((item) => {
        const active = isReaderActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex flex-col items-center gap-0.5 py-2 text-[11px] text-muted-foreground",
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
