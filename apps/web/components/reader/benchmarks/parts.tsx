import type { CSSProperties, ReactNode } from "react";

import { PROVIDERS, type ProviderKey, providerColor, providerKey, providerLabel } from "@/components/reader/benchmarks/provider-colors";
import type { BenchmarkChange } from "@/lib/benchmark-types";
import { cn } from "@/lib/utils";

/** A provider's colour swatch in plain HTML (tables, legends), switching with the theme. */
export function ProviderDot({ org, className }: { org: string | null | undefined; className?: string }) {
  const style = { "--dot-l": providerColor(org, "light"), "--dot-d": providerColor(org, "dark") } as CSSProperties;
  return <span aria-hidden style={style} className={cn("inline-block size-2.5 shrink-0 rounded-full bg-(--dot-l) dark:bg-(--dot-d)", className)} />;
}

/** Legend of the providers present, in palette order, gray "기타" last. */
export function ProviderLegend({ orgs }: { orgs: (string | null | undefined)[] }) {
  const present = new Set<ProviderKey>(orgs.map(providerKey));
  const keys: ProviderKey[] = [...PROVIDERS.map((p) => p.key).filter((key) => present.has(key)), ...(present.has("other") ? (["other"] as const) : [])];
  return (
    <ul aria-label="제공사 색" className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {keys.map((key) => (
        <li key={key} className="flex items-center gap-1.5">
          <ProviderDot org={key === "other" ? null : key} className="size-2 rounded-[2px]" />
          {providerLabel(key)}
        </li>
      ))}
    </ul>
  );
}

/** NEW, ▲n or ▼n against the previous snapshot; nothing when unchanged or unknown. */
export function ChangeMark({ change, by }: { change: BenchmarkChange | null; by: number }) {
  if (change === "new")
    return (
      <span role="img" aria-label="새로 진입" className="text-[10px] font-bold text-primary">
        NEW
      </span>
    );
  if (change === "up" && by > 0)
    return (
      <span role="img" aria-label={`${by}계단 상승`} className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
        {`▲${by}`}
      </span>
    );
  if (change === "down" && by > 0)
    return (
      <span role="img" aria-label={`${by}계단 하락`} className="text-[10px] font-semibold text-rose-600 dark:text-rose-400">
        {`▼${by}`}
      </span>
    );
  return null;
}

/** A pressed/unpressed chip: the sites' "Open weights" style filters. */
export function ToggleChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 items-center rounded-full border px-3 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
        pressed ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** A row of mutually exclusive buttons (axis, effort level). */
export function Segmented<K extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex h-7 items-stretch overflow-hidden rounded-md border text-xs">
      {options.map((option, index) => (
        <button
          key={option.key}
          type="button"
          aria-pressed={value === option.key}
          onClick={() => onChange(option.key)}
          className={cn(
            "px-2.5 whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-inset",
            index > 0 && "border-l",
            value === option.key ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Tooltip box shared by the scatter and bar charts. */
export function TipBox({ title, org, lines }: { title: string; org?: string | null; lines: [string, string][] }) {
  return (
    <div className="grid min-w-40 gap-1 rounded-lg border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur">
      <div className="flex items-center gap-1.5 font-medium">
        {org !== undefined && <ProviderDot org={org} className="size-2" />}
        {title}
      </div>
      {org && <div className="text-muted-foreground">{org}</div>}
      {lines.map(([name, value]) => (
        <div key={name} className="flex justify-between gap-3">
          <span className="text-muted-foreground">{name}</span>
          <span className="font-medium tabular-nums">{value}</span>
        </div>
      ))}
    </div>
  );
}
