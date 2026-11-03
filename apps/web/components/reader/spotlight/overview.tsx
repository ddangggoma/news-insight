import { ChevronRight } from "lucide-react";

import { AppLink as Link } from "@/components/app-link";
import { EMPTY_SECTION } from "@/components/reader/spotlight/section-list";
import { SECTION_KEYS, SECTION_LABEL, type SpotlightView, spotlightHref } from "@/lib/spotlight-types";

const TOP = 3;

/** The 전체 tab: Opus's one-line headline and the top three of every section. */
export function Overview({ view }: { view: SpotlightView }) {
  return (
    <div className="space-y-5">
      {view.headline ? (
        <p className="rounded-lg border bg-muted/40 px-4 py-3 text-base font-medium leading-relaxed">{view.headline}</p>
      ) : (
        view.date === null && <p className="text-sm text-muted-foreground">아직 발행된 목록이 없습니다.</p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {SECTION_KEYS.map((key) => {
          const top = view.sections[key].slice(0, TOP);
          return (
            <section key={key} className="rounded-lg border p-4">
              <h2 className="mb-2 text-sm font-semibold">
                <Link href={spotlightHref(key, view.date)} className="inline-flex items-center gap-0.5 hover:text-primary">
                  {SECTION_LABEL[key]}
                  <ChevronRight className="size-4" aria-hidden />
                </Link>
              </h2>
              {top.length === 0 ? (
                <p className="py-3 text-sm text-muted-foreground">{EMPTY_SECTION}</p>
              ) : (
                <ol className="space-y-2">
                  {top.map((entry) => (
                    <li key={entry.key} className="flex gap-2.5">
                      <span className="w-5 shrink-0 text-right font-semibold tabular-nums">{entry.rank}</span>
                      <div className="min-w-0">
                        {entry.url ? (
                          <a href={entry.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium leading-snug hover:text-primary hover:underline">
                            {entry.title_ko}
                          </a>
                        ) : (
                          <span className="text-sm font-medium leading-snug">{entry.title_ko}</span>
                        )}
                        {entry.why_hot && <p className="line-clamp-2 text-xs text-muted-foreground">{entry.why_hot}</p>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
