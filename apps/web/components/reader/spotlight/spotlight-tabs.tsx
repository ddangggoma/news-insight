import { AppLink as Link } from "@/components/app-link";
import { SPOTLIGHT_TABS, type SpotlightTab, spotlightHref } from "@/lib/spotlight-types";
import { cn } from "@/lib/utils";

/** The tabs of the 주목 받는 page; `?tab=` and `?date=` stay in the address. New tabs join SPOTLIGHT_TABS. */
export function SpotlightTabs({ active, date }: { active: SpotlightTab; date: string | null }) {
  return (
    <nav aria-label="주목 받는 보기" className="flex gap-1 overflow-x-auto border-b">
      {SPOTLIGHT_TABS.map((tab) => (
        <Link
          key={tab.key}
          href={spotlightHref(tab.key, date)}
          aria-current={active === tab.key ? "page" : undefined}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap",
            active === tab.key ? "border-primary font-semibold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
