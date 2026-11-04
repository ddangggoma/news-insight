import type { ChartConfig } from "@/components/ui/chart";

// A provider keeps one colour on every card and under every filter (colour follows the
// entity, never its rank). The hues are DeepSWE's own family colours (deepswe.datacurve.ai's
// --family-* tokens, light and dark), so the DeepSWE chart reads like the site and the other
// cards agree with it: Anthropic orange, OpenAI green, Google blue. Each provider has its
// own hue, so no mark needs an outline variant.
type Pair = { light: string; dark: string };

const FAMILY = {
  openai: { light: "oklch(58% 0.13 155)", dark: "oklch(75% 0.14 155)" },
  anthropic: { light: "oklch(62% 0.15 50)", dark: "oklch(78% 0.14 50)" },
  google: { light: "oklch(58% 0.17 255)", dark: "oklch(74% 0.16 255)" },
  xai: { light: "oklch(56% 0.08 265)", dark: "oklch(74% 0.08 265)" },
  meta: { light: "oklch(61% 0.2 255)", dark: "oklch(75% 0.18 255)" },
  alibaba: { light: "oklch(60% 0.15 220)", dark: "oklch(76% 0.14 220)" },
  mistral: { light: "oklch(62% 0.16 75)", dark: "oklch(78% 0.15 75)" },
  deepseek: { light: "oklch(55% 0.18 295)", dark: "oklch(72% 0.17 295)" },
  zai: { light: "oklch(62% 0.12 195)", dark: "oklch(78% 0.12 195)" },
  moonshot: { light: "oklch(60% 0.18 20)", dark: "oklch(74% 0.17 20)" },
  minimax: { light: "oklch(62% 0.17 330)", dark: "oklch(76% 0.16 330)" },
  xiaomi: { light: "oklch(65% 0.13 95)", dark: "oklch(80% 0.13 95)" },
  cursor: { light: "oklch(56% 0.03 250)", dark: "oklch(76% 0.03 250)" },
} as const satisfies Record<string, Pair>;

const OTHER: Pair = { light: "oklch(55% 0.02 270)", dark: "oklch(75% 0.02 270)" };

/** Providers with a colour, in legend order (DeepSWE's family order). */
export const PROVIDERS = [
  { key: "openai", label: "OpenAI", aliases: ["openai"] },
  { key: "anthropic", label: "Anthropic", aliases: ["anthropic"] },
  { key: "google", label: "Google", aliases: ["google", "googledeepmind", "deepmind"] },
  { key: "xai", label: "xAI", aliases: ["xai"] },
  { key: "meta", label: "Meta", aliases: ["meta", "metaai", "facebook"] },
  { key: "alibaba", label: "Alibaba", aliases: ["alibaba", "alibabacloud", "qwen", "alibabaqwen"] },
  { key: "mistral", label: "Mistral", aliases: ["mistral", "mistralai"] },
  { key: "deepseek", label: "DeepSeek", aliases: ["deepseek", "deepseekai"] },
  { key: "zai", label: "Z AI", aliases: ["zai", "zhipu", "zhipuai", "glm", "zaiorg"] },
  { key: "moonshot", label: "Moonshot AI", aliases: ["moonshot", "moonshotai", "kimi"] },
  { key: "minimax", label: "MiniMax", aliases: ["minimax", "minimaxai"] },
  { key: "xiaomi", label: "Xiaomi", aliases: ["xiaomi", "xiaomimimo", "mimo"] },
  { key: "cursor", label: "Cursor", aliases: ["cursor", "anysphere"] },
] as const satisfies readonly { key: keyof typeof FAMILY; label: string; aliases: readonly string[] }[];

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
  const key = providerKey(org);
  return (key === "other" ? OTHER : FAMILY[key])[theme];
}

/** Chart config with a `--color-<provider>` variable per provider, both themes. */
export const PROVIDER_CHART_CONFIG = {
  ...Object.fromEntries(PROVIDERS.map((p) => [p.key, { label: p.label, theme: FAMILY[p.key] }])),
  other: { label: "기타", theme: OTHER },
} satisfies ChartConfig;

/** SVG paint for a provider's mark inside a ChartContainer given PROVIDER_CHART_CONFIG. */
export function providerPaint(key: ProviderKey): { fill: string; stroke: string } {
  return { fill: `var(--color-${key})`, stroke: "var(--card)" };
}

export function providerLabel(key: ProviderKey): string {
  return key === "other" ? "기타" : (BY_KEY.get(key)?.label ?? key);
}

/** Legend order: DeepSWE's family order, "기타" last. */
export const PROVIDER_ORDER: ProviderKey[] = [...PROVIDERS.map((p) => p.key), "other"];

// The eight categorical slots of the validated reference palette (dataviz skill), light and
// dark: colours for picks by pick order (two picks from one maker stay apart), not providers.
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

/** Selection colours for a comparison (slots 1-4 by pick order: two picks from one maker stay apart). */
export function slotColor(index: number, theme: "light" | "dark"): string {
  return SLOTS[index % SLOTS.length][theme];
}
