"use client";

import { useEffect, useState } from "react";

import { PersonaCard } from "@/components/reader/persona-card";
import type { BriefingPersona, PublicBriefing } from "@/lib/briefing-types";

const ROLE_KEY = "briefing-role";
const TOP = 5;

/**
 * The reader's own role first (remembered per browser, default the sensing practitioner), then
 * the five roles today's articles matter most to (plan 13 B6). The full roster stays below.
 */
export function PersonaFocus({
  personas,
  refs,
  defaultRole,
}: {
  personas: BriefingPersona[];
  refs: PublicBriefing["refs"];
  defaultRole: string;
}) {
  const [role, setRole] = useState(defaultRole);
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(ROLE_KEY);
      if (saved && personas.some((p) => p.key === saved)) setRole(saved);
    } catch {
      // storage blocked: keep the default role
    }
  }, [personas]);
  const choose = (key: string) => {
    setRole(key);
    try {
      window.localStorage.setItem(ROLE_KEY, key);
    } catch {
      // storage blocked: the choice lasts for this page
    }
  };
  const mine = personas.find((p) => p.key === role);
  const top = personas
    .filter((p) => p.status === "insight" && p.key !== role)
    .map((p, index) => ({ p, index }))
    .sort((a, b) => (b.p.relevance ?? 0) - (a.p.relevance ?? 0) || a.index - b.index)
    .slice(0, TOP)
    .map(({ p }) => p);
  return (
    <div className="space-y-3">
      <label className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        내 역할
        <select
          id="briefing-role"
          value={role}
          onChange={(event) => choose(event.target.value)}
          className="max-w-[60%] rounded-md border bg-background px-2 py-1 text-xs text-foreground"
        >
          {personas.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {mine ? (
        mine.status === "insight" ? (
          <PersonaCard persona={mine} refs={refs} open className="border-primary/40" />
        ) : (
          <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">{mine.name}: 오늘은 이 역할에 해당하는 뚜렷한 신호가 없습니다.</p>
        )
      ) : null}
      {top.length ? <p className="pt-1 text-xs font-medium text-muted-foreground">오늘 관련도가 높은 역할</p> : null}
      {top.map((persona) => (
        <PersonaCard key={persona.key} persona={persona} refs={refs} />
      ))}
    </div>
  );
}
