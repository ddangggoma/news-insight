export const RADAR_SECTIONS = [
  ["signals", "신호"],
  ["landscape", "지도"],
  ["matrix", "포지셔닝"],
  ["timing", "타이밍"],
  ["calendar", "캘린더"],
  ["rank", "순위"],
  ["cloud", "기술"],
  ["engagement", "반응"],
  ["regions", "지역"],
  ["share", "점유율"],
  ["maturity", "신호 단계"],
  ["impact", "기회·위험"],
  ["flows", "확산 경로"],
  ["network", "융합"],
  ["cross", "교차"],
] as const;

/** Jump links to every view; sticks under the site header while scrolling. */
export function SectionNav() {
  return (
    <nav aria-label="레이더 구역" className="z-20 -mx-4 border-b bg-background/85 px-4 py-2 backdrop-blur md:sticky md:top-[59px] md:-mx-6 md:px-6">
      <ul className="flex gap-1 overflow-x-auto [scrollbar-width:none]">
        {RADAR_SECTIONS.map(([id, label]) => (
          <li key={id}>
            <a href={`#${id}`} className="block rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
