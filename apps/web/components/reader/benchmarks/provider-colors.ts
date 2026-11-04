import type { ChartConfig } from "@/components/ui/chart";

// The eight categorical slots of the validated reference palette (dataviz skill) — slots 1-4
// are the ones components/console/card-progress-charts.tsx already uses — light and dark
// steps. A provider keeps its mark on every site and under every filter (colour follows the
// entity, never its rank). The palette has no validated ninth hue (extra hues fail the CVD and
// chroma checks), so three more providers get a hollow mark on the three best-separated slots
// instead of a new hue; anyone else is the neutral gray "기타".
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

/** Providers with a mark, in legend order; `hollow` marks reuse a slot as an outline. */
export const PROVIDERS = [
  { key: "openai", label: "OpenAI", slot: 0, hollow: false, aliases: ["openai"] },
  { key: "google", label: "Google", slot: 1, hollow: false, aliases: ["google", "googledeepmind", "deepmind"] },
  { key: "anthropic", label: "Anthropic", slot: 2, hollow: false, aliases: ["anthropic"] },
  { key: "xai", label: "xAI", slot: 3, hollow: false, aliases: ["xai"] },
  { key: "meta", label: "Meta", slot: 4, hollow: false, aliases: ["meta", "metaai", "facebook"] },
  { key: "deepseek", label: "DeepSeek", slot: 5, hollow: false, aliases: ["deepseek", "deepseekai"] },
  { key: "alibaba", label: "Alibaba", slot: 6, hollow: false, aliases: ["alibaba", "alibabacloud", "qwen", "alibabaqwen"] },
  { key: "zai", label: "Z AI", slot: 7, hollow: false, aliases: ["zai", "zhipu", "zhipuai", "glm", "zaiorg"] },
  { key: "moonshot", label: "Moonshot AI", slot: 0, hollow: true, aliases: ["moonshot", "moonshotai", "kimi"] },
  { key: "minimax", label: "MiniMax", slot: 1, hollow: true, aliases: ["minimax", "minimaxai"] },
  { key: "mistral", label: "Mistral", slot: 2, hollow: true, aliases: ["mistral", "mistralai"] },
] as const;

export type ProviderKey = (typeof PROVIDERS)[number]["key"] | "other";

const BY_ALIAS = new Map<string, ProviderKey>(PROVIDERS.flatMap((p) => p.aliases.map((alias) => [alias, p.key] as const)));
const BY_KEY = new Map<string, (typeof PROVIDERS)[number]>(PROVIDERS.map((p) => [p.key, p]));

/** "Google DeepMind", "google" and "GOOGLE" are one provider; anything unknown is "other". */
export function providerKey(org: string | null | undefined): ProviderKey {
  if (!org) return "other";
  const key = org.toLowerCase().replace(/[^a-z0-9]+/g, "");
  return BY_KEY.has(key) ? (key as ProviderKey) : (BY_ALIAS.get(key) ?? "other");
}

export function providerColor(org: string | null | undefined, theme: "light" | "dark"): string {
  const provider = BY_KEY.get(providerKey(org));
  return (provider ? SLOTS[provider.slot] : OTHER)[theme];
}

export function isHollow(key: ProviderKey): boolean {
  return BY_KEY.get(key)?.hollow ?? false;
}

/** Chart config with a `--color-<provider>` variable per provider, both themes. */
export const PROVIDER_CHART_CONFIG = {
  ...Object.fromEntries(PROVIDERS.map((p) => [p.key, { label: p.label, theme: SLOTS[p.slot] }])),
  other: { label: "기타", theme: OTHER },
} satisfies ChartConfig;

/** SVG paint for a provider's mark inside a ChartContainer given PROVIDER_CHART_CONFIG. */
export function providerPaint(key: ProviderKey): { fill: string; fillOpacity: number; stroke: string } {
  const color = `var(--color-${key})`;
  return isHollow(key) ? { fill: color, fillOpacity: 0.15, stroke: color } : { fill: color, fillOpacity: 1, stroke: "var(--card)" };
}

export function providerLabel(key: ProviderKey): string {
  return key === "other" ? "기타" : (BY_KEY.get(key)?.label ?? key);
}

/** Legend order: palette order, "기타" last. */
export const PROVIDER_ORDER: ProviderKey[] = [...PROVIDERS.map((p) => p.key), "other"];

/** Selection colours for a comparison (slots 1-4 by pick order: two picks from one maker stay apart). */
export function slotColor(index: number, theme: "light" | "dark"): string {
  return SLOTS[index % SLOTS.length][theme];
}
