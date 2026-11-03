import type { ChartConfig } from "@/components/ui/chart";

// The eight categorical slots of the validated reference palette (dataviz skill) — slots 1-4
// are the ones components/console/card-progress-charts.tsx already uses — light and dark
// steps. A provider keeps its slot on every site and under every filter (colour follows the
// entity, never its rank); makers past the eighth fold into the neutral gray "기타".
const SLOTS = [
  { light: "#2a78d6", dark: "#3987e5" }, // blue
  { light: "#eb6834", dark: "#d95926" }, // orange
  { light: "#1baf7a", dark: "#199e70" }, // aqua
  { light: "#eda100", dark: "#c98500" }, // yellow
  { light: "#e87ba4", dark: "#d55181" }, // magenta
  { light: "#008300", dark: "#008300" }, // green
  { light: "#6250d6", dark: "#9085e9" }, // violet
  { light: "#e34948", dark: "#e66767" }, // red
] as const;

const OTHER = { light: "#9aa3b0", dark: "#6b7380" } as const;

/** Providers with a slot, in slot order; the label is how the legend names them. */
export const PROVIDERS = [
  { key: "openai", label: "OpenAI", aliases: ["openai"] },
  { key: "google", label: "Google", aliases: ["google", "googledeepmind", "deepmind"] },
  { key: "anthropic", label: "Anthropic", aliases: ["anthropic"] },
  { key: "xai", label: "xAI", aliases: ["xai"] },
  { key: "meta", label: "Meta", aliases: ["meta", "metaai", "facebook"] },
  { key: "deepseek", label: "DeepSeek", aliases: ["deepseek", "deepseekai"] },
  { key: "alibaba", label: "Alibaba", aliases: ["alibaba", "alibabacloud", "qwen", "alibabaqwen"] },
  { key: "mistral", label: "Mistral", aliases: ["mistral", "mistralai"] },
] as const;

export type ProviderKey = (typeof PROVIDERS)[number]["key"] | "other";

const BY_ALIAS = new Map<string, ProviderKey>(PROVIDERS.flatMap((p) => p.aliases.map((alias) => [alias, p.key] as const)));

/** "Google DeepMind", "google" and "GOOGLE" are one provider; anything unknown is "other". */
export function providerKey(org: string | null | undefined): ProviderKey {
  if (!org) return "other";
  return BY_ALIAS.get(org.toLowerCase().replace(/[^a-z0-9]+/g, "")) ?? "other";
}

export function providerColor(org: string | null | undefined, theme: "light" | "dark"): string {
  const key = providerKey(org);
  const index = PROVIDERS.findIndex((p) => p.key === key);
  return (index < 0 ? OTHER : SLOTS[index])[theme];
}

/** Chart config with a `--color-<provider>` variable per provider, both themes. */
export const PROVIDER_CHART_CONFIG = {
  ...Object.fromEntries(PROVIDERS.map((p, index) => [p.key, { label: p.label, theme: SLOTS[index] }])),
  other: { label: "기타", theme: OTHER },
} satisfies ChartConfig;

/** Fill for a mark inside a ChartContainer given PROVIDER_CHART_CONFIG. */
export function providerVar(org: string | null | undefined): string {
  return `var(--color-${providerKey(org)})`;
}

export function providerLabel(key: ProviderKey): string {
  return key === "other" ? "기타" : (PROVIDERS.find((p) => p.key === key)?.label ?? key);
}

/** Selection colours for a comparison (slots 1-4 by pick order: two picks from one maker stay apart). */
export function slotColor(index: number, theme: "light" | "dark"): string {
  return SLOTS[index % SLOTS.length][theme];
}
