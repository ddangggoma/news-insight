import { AppLink as Link } from "@/components/app-link";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "roadmap", href: "/roadmap", label: "성숙도·로드맵" },
  { key: "board", href: "/board", label: "기회·위협 보드" },
] as const;

/** The two views under the 로드맵 menu (2026-10-12): maturity/roadmap and the opportunity board. */
export function RoadmapTabs({ active }: { active: (typeof TABS)[number]["key"] }) {
  return (
    <nav aria-label="로드맵 보기" className="flex gap-1 border-b">
      {TABS.map((tab) => (
        <Link
          key={tab.key}
          href={tab.href}
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
