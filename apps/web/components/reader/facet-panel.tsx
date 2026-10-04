"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import type { Facets } from "@/lib/reader-types";
import {
  AXIS_LABELS,
  type Axis,
  type ReaderFilters,
  SCOPES,
  type Scope,
  setHref,
  toggleHref,
} from "@/lib/reader-filters";
import { cn } from "@/lib/utils";

const SECTIONS: { axis: Axis; title: string; limit?: number }[] = [
  { axis: "field", title: "기술 분야", limit: 10 },
  { axis: "theme", title: "테마" },
  { axis: "business", title: "DX 사업부" },
  { axis: "impact", title: "영향" },
  { axis: "track", title: "트랙" },
  { axis: "region", title: "지역" },
];

const TRACK_DOT: Record<string, string> = {
  news: "bg-track-news",
  community: "bg-track-community",
  research_ip: "bg-track-research",
  oss: "bg-track-oss",
};

function keysFor(axis: Axis, filters: ReaderFilters): string[] {
  const all = Object.keys(AXIS_LABELS[axis]);
  // themes only make sense under a chosen field
  return axis === "theme" ? all.filter((key) => filters.field.some((field) => key.startsWith(`${field}__`))) : all;
}

export function FacetPanel({ facets, filters }: { facets: Facets; filters: ReaderFilters }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [expanded, setExpanded] = useState<Partial<Record<Axis, boolean>>>({});
  const go = (href: string) => startTransition(() => router.push(href, { scroll: false }));

  return (
    <div className={cn("space-y-6 transition-opacity", pending && "opacity-60")} aria-busy={pending}>
      <fieldset className="space-y-1">
        <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">범위</legend>
        {(Object.keys(SCOPES) as Scope[]).map((scope) => (
          <Link
            key={scope}
            href={setHref(filters, "scope", scope)}
            scroll={false}
            aria-current={filters.scope === scope ? "true" : undefined}
            className={cn(
              "flex items-center justify-between rounded-md px-2 py-1 text-sm text-ink-2 hover:bg-muted",
              filters.scope === scope && "bg-primary/10 font-semibold text-foreground",
            )}
          >
            {SCOPES[scope]}
          </Link>
        ))}
      </fieldset>
      {SECTIONS.map(({ axis, title, limit }) => {
        const counts = facets[axis] ?? {};
        const keys = keysFor(axis, filters).sort(
          (a, b) => (counts[b] ?? 0) - (counts[a] ?? 0) || AXIS_LABELS[axis][a].localeCompare(AXIS_LABELS[axis][b], "ko"),
        );
        if (!keys.length) return null;
        const shown = limit && !expanded[axis] ? keys.slice(0, limit) : keys;
        return (
          <fieldset key={axis} className="space-y-0.5">
            <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">{title}</legend>
            {shown.map((key) => {
              const id = `facet-${axis}-${key}`;
              const count = counts[key] ?? 0;
              const checked = filters[axis].includes(key);
              return (
                <label
                  key={key}
                  htmlFor={id}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm text-ink-2 hover:bg-muted",
                    checked && "bg-primary/10 font-semibold text-foreground",
                    !count && !checked && "opacity-50",
                  )}
                >
                  <input
                    // uncontrolled so the click shows at once; the key resyncs it with the URL
                    key={`${id}-${checked}`}
                    id={id}
                    type="checkbox"
                    defaultChecked={checked}
                    onChange={() => go(toggleHref(filters, axis, key))}
                    className="size-4 accent-primary"
                  />
                  {axis === "track" ? <span className={cn("size-2 rounded-full", TRACK_DOT[key])} aria-hidden /> : null}
                  <span className="min-w-0 flex-1 truncate">{AXIS_LABELS[axis][key]}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
                </label>
              );
            })}
            {limit && keys.length > limit ? (
              <button
                type="button"
                onClick={() => setExpanded((state) => ({ ...state, [axis]: !state[axis] }))}
                className="px-2 py-1 text-xs font-medium text-primary"
              >
                {expanded[axis] ? "접기" : `+ ${keys.length - limit}개 더 보기`}
              </button>
            ) : null}
          </fieldset>
        );
      })}
    </div>
  );
}
