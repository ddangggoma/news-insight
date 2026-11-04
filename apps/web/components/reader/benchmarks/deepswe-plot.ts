/**
 * The geometry of DeepSWE's own "score against cost" chart (deepswe.datacurve.ai), rebuilt
 * from the rules its page draws with: one dot per configuration, one line per model through
 * its effort levels, one two-line label per model placed clear of the others, the x axis
 * reversed so the efficient corner is top right. Pure functions, so the chart component only
 * draws what this returns.
 */
import { type ProviderKey, providerColor } from "@/components/reader/benchmarks/provider-colors";
import type { DsPoint } from "@/lib/benchmark-view";

export type Axis = "cost" | "tokens" | "steps";

// ---- names, effort, defaults ---------------------------------------------------------

const EFFORT_ORDER: Record<string, number> = { none: 0, minimal: 1, low: 2, medium: 3, high: 4, xhigh: 5, max: 6 };

/** none → max in order; an unknown level after them all, no level before them all. */
export function effortRank(effort: string | null): number {
  return effort ? (EFFORT_ORDER[effort.toLowerCase()] ?? 50) : -1;
}

/** The site's name: "gpt-5-6-sol" → "gpt-5.6-sol", "gemini-3-1-pro-preview" → "gemini-3.1-pro". */
export function displayName(model: string): string {
  return model
    .replace(/^[a-z0-9-]+\//, "")
    .replace(/(\d)-(\d)(?=-|$)/g, "$1.$2")
    .replace(/-preview$/, "");
}

/** The effort level the site labels for a model; any other model labels its highest. */
export const DEFAULT_EFFORT: Record<string, string> = {
  "gpt-6-astra": "xhigh",
  "gpt-5-6-sol": "medium",
  "gpt-5-6-terra": "medium",
  "gpt-5-6-luna": "medium",
  "gpt-5-5": "medium",
  "claude-opus-4-8": "high",
  "claude-opus-4-7": "xhigh",
  "claude-fable-5": "high",
  "claude-sonnet-5": "high",
  "gemini-3-5-flash": "high",
  "gemini-3-7-flash": "medium",
  "muse-spark-1-1": "medium",
};

/** Configurations dearer than this per task start hidden (the site's chart keeps its x range readable). */
const MAX_DEFAULT_COST = 15;

/** Each model's best pass@1 (percent), best first. */
export function bestByModel(points: Pick<DsPoint, "model" | "score">[]): { model: string; best: number }[] {
  const best = new Map<string, number>();
  for (const p of points) best.set(p.model, Math.max(best.get(p.model) ?? 0, p.score));
  return [...best.entries()].map(([model, value]) => ({ model, best: value })).sort((a, b) => b.best - a.best);
}

/**
 * The configurations the chart opens with: the site's "Configs (57/70)", i.e. the default
 * models' configurations (`shown`: the API ranks exactly the models the site opens on, best
 * pass rate of 5% or more minus the few it hides) that cost at most $15 a task.
 */
export function defaultConfigs(points: Pick<DsPoint, "id" | "shown" | "cost">[]): Set<string> {
  return new Set(points.filter((p) => p.shown && (p.cost ?? 0) <= MAX_DEFAULT_COST).map((p) => p.id));
}

// ---- colour --------------------------------------------------------------------------

/** The site's maker by model name, on our palette's keys. */
export function family(model: string): ProviderKey {
  const lower = model.toLowerCase();
  const n = `${lower.includes("/") ? lower.slice(lower.lastIndexOf("/") + 1) : lower} ${displayName(model).toLowerCase()}`;
  const has = (s: string) => n.includes(s);
  if (has("gpt-") || has("o1-") || has("o3-") || has("o4-")) return "openai";
  if (has("claude-")) return "anthropic";
  if (has("gemini-")) return "google";
  if (has("grok-")) return "xai";
  if (has("muse-")) return "meta";
  if (has("glm-")) return "zai";
  if (has("kimi-")) return "moonshot";
  if (has("deepseek-")) return "deepseek";
  if (has("mistral-")) return "mistral";
  if (has("mimo-")) return "xiaomi";
  if (has("minimax")) return "minimax";
  if (has("qwen")) return "alibaba";
  if (has("composer-")) return "cursor";
  return "other";
}

export interface Shade {
  light: string;
  dark: string;
}

const familyShade = (key: ProviderKey): Shade => ({ light: providerColor(key, "light"), dark: providerColor(key, "dark") });

/** sRGB channels (0–1) of a `#rrggbb` or `oklch(L% C H)` colour, clipped to the gamut. */
function toRgb(color: string): [number, number, number] {
  if (color.startsWith("#")) {
    const n = Number.parseInt(color.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255) as [number, number, number];
  }
  const match = /oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)/.exec(color);
  if (!match) throw new Error(`unsupported colour ${color}`);
  const [L, C, H] = [Number(match[1]) / 100, Number(match[2]), (Number(match[3]) * Math.PI) / 180];
  const [a, b] = [C * Math.cos(H), C * Math.sin(H)];
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const linear = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return linear.map((v) => Math.min(1, Math.max(0, v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055))) as [number, number, number];
}

/** HSL of a `#rrggbb`, `oklch(…)` or `hsl(h s% l%)` colour: hue in degrees, saturation and lightness in percent. */
export function toHsl(color: string): [number, number, number] {
  const hsl = /^hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)$/.exec(color);
  if (hsl) return [Number(hsl[1]), Number(hsl[2]), Number(hsl[3])];
  const [r, g, b] = toRgb(color);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l * 100];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s * 100, l * 100];
}

/** The colour with its HSL lightness moved by `delta` points, kept within 25–82 like the site. */
export function shiftLightness(color: string, delta: number): string {
  if (delta === 0) return color;
  const [h, s, l] = toHsl(color);
  const next = Math.min(82, Math.max(25, l + delta));
  return `hsl(${h.toFixed(1)} ${s.toFixed(1)}% ${next.toFixed(1)}%)`;
}

// Each next model of a maker steps lighter in both themes: on the dark card a darker step
// would sink the low-ranked models into the background.
const SHADE_DIRECTION = { light: 1, dark: 1 } as const;

/** A model's label colour: its maker's. */
export function labelShade(model: string): Shade {
  return familyShade(family(model));
}

/**
 * A model's mark colour: its maker's hue, each next-best model of the maker a step lighter,
 * 8 points a step for OpenAI's many models, 11 for the rest.
 */
export function modelShades(points: Pick<DsPoint, "model" | "score">[]): Map<string, Shade> {
  const byFamily = new Map<ProviderKey, string[]>();
  for (const { model } of bestByModel(points)) {
    const key = family(model);
    byFamily.set(key, [...(byFamily.get(key) ?? []), model]);
  }
  const shades = new Map<string, Shade>();
  for (const [key, models] of byFamily) {
    const step = key === "openai" ? 8 : 11;
    const base = familyShade(key);
    models.forEach((model, index) => shades.set(model, {
        light: shiftLightness(base.light, SHADE_DIRECTION.light * step * index),
        dark: shiftLightness(base.dark, SHADE_DIRECTION.dark * step * index),
      }));
  }
  return shades;
}

// ---- axes ----------------------------------------------------------------------------

export const AXES: Record<Axis, { label: string; title: string; value: (p: DsPoint) => number | null; format: (v: number) => string }> = {
  cost: { label: "비용", title: "작업당 평균 비용", value: (p) => p.cost, format: formatCost },
  tokens: { label: "출력 토큰", title: "작업당 평균 출력 토큰", value: (p) => p.tokens, format: formatTokens },
  steps: { label: "에이전트 단계", title: "작업당 평균 에이전트 단계", value: (p) => p.steps, format: (v) => v.toFixed(0) },
};

/** $0, $0.50, $5.00, $10. */
export function formatCost(v: number): string {
  if (v >= 10) return `$${v.toFixed(0)}`;
  if (v >= 0.01) return `$${v.toFixed(2)}`;
  return `$${v.toPrecision(1)}`;
}

/** 50k, 1.5k, 2.3M. */
export function formatTokens(v: number): string {
  const n = Math.abs(v);
  if (n >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (n >= 1e4) return `${Math.round(v / 1e3)}k`;
  if (n >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
  if (n >= 100) return v.toFixed(0);
  if (n >= 10) return v.toFixed(1);
  return v.toFixed(2).replace(/\.?0+$/, "");
}

/** 0 to `max` in steps of 1, 2, 5 or 10 × 10^k, about `count` of them. */
export function niceTicks(max: number, count = 6): number[] {
  if (!(max > 0)) return [0];
  const raw = max / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const ratio = raw / power;
  const step = (ratio >= 5 ? 10 : ratio >= 2 ? 5 : ratio >= 1 ? 2 : 1) * power;
  const ticks: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

// ---- layout --------------------------------------------------------------------------

export interface Dims {
  W: number;
  H: number;
  M: { top: number; right: number; bottom: number; left: number };
  mobile: boolean;
  plotW: number;
  plotH: number;
  /** In the frame's own units; `sub` is a label's second line (the effort level). */
  font: { title: number; tick: number; axis: number; eff: number; label: number; hover: number; sub: number };
}

/**
 * The site's frames: 440×500 under 640 px, else 600–1200 wide at 1.6:1 (900 when unmeasured).
 * Text is sized so it reads at least 12 px on screen (tick labels 11 px): the desktop frame is
 * drawn at its own size, the narrow one scaled down to the container, so its fonts grow by
 * that scale.
 */
export function dims(width: number | null): Dims {
  if (width !== null && width < 640) {
    const M = { top: 40, right: 68, bottom: 52, left: 46 };
    const k = 440 / Math.max(width, 280);
    const font = { title: 13 * k, tick: 11 * k, axis: 12 * k, eff: 12 * k, label: 12 * k, hover: 12 * k, sub: 12 * k };
    return { W: 440, H: 500, M, mobile: true, plotW: 440 - M.left - M.right, plotH: 500 - M.top - M.bottom, font };
  }
  const W = Math.round(Math.min(1200, Math.max(600, width ?? 900)));
  const H = Math.round(W / 1.6);
  const M = { top: 40, right: 60, bottom: 52, left: 46 };
  return { W, H, M, mobile: false, plotW: W - M.left - M.right, plotH: H - M.top - M.bottom, font: { title: 14, tick: 12, axis: 13, eff: 12, label: 13, hover: 12, sub: 12 } };
}

export interface PlotPoint {
  id: string;
  model: string;
  effort: string | null;
  /** Metric value and pass rate (0–1). */
  x: number;
  y: number;
  px: number;
  py: number;
  labeled: boolean;
}

export interface PlotLine {
  key: string;
  model: string;
  /** The point a hover on the line stands for: the labelled one. */
  hoverId: string;
  /** Points in effort order. */
  ids: string[];
  d: string;
}

export interface PlotLabel {
  id: string;
  model: string;
  line1: string;
  line2: string | null;
  x: number;
  y: number;
  anchor: "start" | "middle" | "end";
  leader: boolean;
  px: number;
  py: number;
  /** The space the label takes (estimated from its text). */
  box: { x: number; y: number; w: number; h: number };
}

export interface Plot {
  dims: Dims;
  points: PlotPoint[];
  lines: PlotLine[];
  labels: PlotLabel[];
  xTicks: number[];
  yTicks: number[];
  X: (v: number) => number;
  Y: (v: number) => number;
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
type Offset = { dx: number; dy: number; anchor: PlotLabel["anchor"] };

const overlap = (a: Box, b: Box) =>
  Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

// beside the point at growing distances: nearer first, a sideways step counting 0.7 of a vertical one
const GRID: Offset[] = (() => {
  const grid: Offset[] = [];
  for (const dy of [0, -8, 10, -16, 18, -24, 26, -32, 34]) {
    for (const dx of [7, 12, 18, 26, 36]) grid.push({ dx, dy, anchor: "start" }, { dx: -dx, dy, anchor: "end" });
    if (dy !== 0) grid.push({ dx: 0, dy, anchor: "middle" });
  }
  return grid.sort((a, b) => Math.abs(a.dy) + Math.abs(a.dx) * 0.7 - (Math.abs(b.dy) + Math.abs(b.dx) * 0.7));
})();

const DOT = 4;
const MAX_OVERLAP = 24;

/**
 * Everything the chart draws for these configurations on this metric, in SVG units of the
 * frame for `width`; null when no configuration has the metric.
 */
export function buildPlot(rows: DsPoint[], axis: Axis, width: number | null): Plot | null {
  const metric = AXES[axis];
  const points: (PlotPoint & { group: string })[] = [];
  for (const row of rows) {
    const x = metric.value(row);
    if (x === null || !Number.isFinite(x) || x <= 0) continue;
    points.push({ id: row.id, model: row.model, effort: row.effort, group: `${row.harness ?? ""}::${row.model}`, x, y: row.score / 100, px: 0, py: 0, labeled: false });
  }
  if (!points.length) return null;

  const groups = new Map<string, typeof points>();
  for (const p of points) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  for (const group of groups.values()) {
    group.sort((a, b) => effortRank(a.effort) - effortRank(b.effort));
    const preferred = DEFAULT_EFFORT[group[0].model];
    const labeled = (preferred ? group.find((p) => (p.effort ?? "").toLowerCase() === preferred) : undefined) ?? group[group.length - 1];
    labeled.labeled = true;
  }

  const d = dims(width);
  const { M, plotW, plotH, font } = d;
  const xMax = Math.max(...points.map((p) => p.x)) * 1.04;
  const yMax = Math.max(0.8, Math.ceil(Math.max(...points.map((p) => p.y)) * 10) / 10);
  const X = (v: number) => M.left + (1 - v / xMax) * plotW;
  const Y = (v: number) => M.top + (1 - v / yMax) * plotH;
  for (const p of points) {
    p.px = X(p.x);
    p.py = Y(p.y);
  }
  const yTicks: number[] = [];
  const yStep = d.mobile ? 0.2 : 0.1;
  for (let v = 0; v <= yMax + 1e-9; v += yStep) yTicks.push(Math.round(v * 100) / 100);

  const lines: PlotLine[] = [];
  for (const [key, group] of groups) {
    if (group.length < 2) continue;
    lines.push({
      key,
      model: group[0].model,
      hoverId: (group.find((p) => p.labeled) ?? group[0]).id,
      ids: group.map((p) => p.id),
      d: group.map((p, i) => `${i === 0 ? "M" : "L"} ${p.px.toFixed(1)} ${p.py.toFixed(1)}`).join(" "),
    });
  }

  // labels, best first, each where it overlaps the placed labels and every dot least
  const inside = (b: Box) => b.x >= 1 && b.x + b.w <= d.W - 1 && b.y >= 1 && b.y + b.h <= d.H - 1;
  const dots: Box[] = points.map((p) => ({ x: p.px - DOT, y: p.py - DOT, w: DOT * 2, h: DOT * 2 }));
  const placed: Box[] = [];
  const labels: PlotLabel[] = [];
  for (const p of points.filter((q) => q.labeled).sort((a, b) => b.y - a.y)) {
    const line1 = displayName(p.model);
    const w = Math.max(line1.length * font.label * 0.52, (p.effort?.length ?? 0) * font.sub * 0.62);
    // one line is about a font's cap height tall; the effort line sits one `sub` below it
    const h = p.effort ? font.label * 0.8 + font.sub + 1 : font.label;
    const ascent = font.label * 0.6;
    const boxAt = (o: Offset): Box => ({
      x: o.anchor === "start" ? p.px + o.dx : o.anchor === "end" ? p.px + o.dx - w : p.px + o.dx - w / 2,
      y: p.py + o.dy - ascent,
      w,
      h,
    });
    const above: Offset = { dx: 0, dy: ascent - h - 5, anchor: "middle" };
    const below: Offset = { dx: 0, dy: ascent + 6, anchor: "middle" };
    const others = [...placed, ...dots];
    let pick: { o: Offset; box: Box } | null = null;
    let least = Number.POSITIVE_INFINITY;
    for (const o of [above, below, ...GRID]) {
      const box = boxAt(o);
      if (!inside(box)) continue;
      const area = others.reduce((sum, b) => sum + overlap(box, b), 0);
      if (area <= MAX_OVERLAP) {
        pick = { o, box };
        break;
      }
      if (area < least) {
        least = area;
        pick = { o, box };
      }
    }
    pick ??= { o: above, box: boxAt(above) };
    // the narrow frame has no room for every name at a readable size: a label that would
    // cover another (or its dots) by more than a twentieth of itself is left off there; the
    // point keeps its colour, its values show on hover, and the table below names it
    const crowded = pick.box.w * pick.box.h * 0.05;
    if (d.mobile && others.reduce((sum, b) => sum + overlap(pick.box, b), 0) > crowded) continue;
    placed.push(pick.box);
    const gapX = Math.max(pick.box.x - p.px, p.px - (pick.box.x + pick.box.w), 0);
    const gapY = Math.max(pick.box.y - p.py, p.py - (pick.box.y + pick.box.h), 0);
    labels.push({
      id: p.id,
      model: p.model,
      line1,
      line2: p.effort,
      x: p.px + pick.o.dx,
      y: p.py + pick.o.dy,
      anchor: pick.o.anchor,
      leader: Math.hypot(gapX, gapY) > 12,
      px: p.px,
      py: p.py,
      box: pick.box,
    });
  }

  return {
    dims: d,
    points: points.map(({ group: _group, ...p }) => p),
    lines,
    labels,
    xTicks: niceTicks(xMax, d.mobile ? 4 : 6),
    yTicks,
    X,
    Y,
  };
}
