import { withQuery } from "@/lib/query";
import type { Scope } from "@/lib/reader-filters";
import type { Radar, RadarKind, Topic, TopicKind, TopicState, TrackMix } from "@/lib/reader-types";
import type { Region } from "@/lib/types";
import { BUSINESS_LABEL, FIELD_LABEL, THEME_LABEL } from "@/lib/taxonomy";

export const RADAR_KINDS: Record<RadarKind, string> = { day: "일간", week: "주간", month: "월간", quarter: "분기" };

export function isRadarKind(value: string): value is RadarKind {
  return value in RADAR_KINDS;
}

/** "the previous N periods" in the reader's words: 7주, 7개월 … */
export const BASELINE_UNIT: Record<RadarKind, string> = { day: "일", week: "주", month: "개월", quarter: "분기" };

export const STATE_META: Record<TopicState, { label: string; hint: string }> = {
  new: { label: "신규", hint: "직전 기간들에 없다가 2곳 이상 출처에서 처음 등장" },
  surging: { label: "급상승", hint: "직전 기간 평균 대비 2σ 이상, 1.5배 이상" },
  rising: { label: "상승", hint: "직전 기간 평균의 1.3배 이상" },
  steady: { label: "유지", hint: "직전 기간 평균과 비슷" },
  falling: { label: "하락", hint: "직전 기간 평균의 70% 이하" },
};
export const STATE_ORDER: TopicState[] = ["new", "surging", "rising", "steady", "falling"];

// ── view state in the URL ────────────────────────────────────────────────────────────────

export type Focus = { kind: TopicKind; key: string };

export type RadarView = {
  scope: Scope;
  business: string[];
  field: string | null;
  focus: Focus | null;
};

export function parseFocus(value: string | undefined): Focus | null {
  if (!value) return null;
  const at = value.indexOf(":");
  const kind = value.slice(0, at);
  const key = value.slice(at + 1);
  if (at < 1 || !key) return null;
  if (kind === "field") return key in FIELD_LABEL ? { kind, key } : null;
  if (kind === "theme") return key in THEME_LABEL ? { kind, key } : null;
  if (kind === "keyword") return key.length <= 200 ? { kind, key } : null;
  return null;
}

export function focusParam(focus: Focus): string {
  return `${focus.kind}:${focus.key}`;
}

export function sameFocus(a: Focus | null, b: Focus | null): boolean {
  return !!a && !!b && a.kind === b.kind && a.key === b.key;
}

export function radarHref(kind: string, key: string, view: Partial<RadarView>): string {
  return withQuery(`/radar/${kind}/${key}`, {
    scope: view.scope && view.scope !== "relevant" ? view.scope : undefined,
    business: view.business?.length ? view.business : undefined,
    field: view.field ?? undefined,
    focus: view.focus ? focusParam(view.focus) : undefined,
  });
}

/** API filters for a view: the field drill-down and DX businesses narrow every number. */
export function radarFilters(view: RadarView): Record<string, string | string[] | undefined> {
  return { scope: view.scope, business: view.business, field: view.field ?? undefined };
}

// ── labels and numbers ───────────────────────────────────────────────────────────────────

export function topicLabel(kind: TopicKind, topic: Pick<Topic, "key" | "label">): string {
  if (kind === "field") return FIELD_LABEL[topic.key] ?? topic.key;
  if (kind === "theme") return THEME_LABEL[topic.key] ?? topic.key;
  return topic.label ?? topic.key;
}

export function businessShort(key: string): string {
  return (BUSINESS_LABEL[key] ?? key).split(" · ")[0];
}

/** Axis label for a period key: W40, 9월, Q3, 10/4. */
export function periodLabel(key: string): string {
  let match = /^\d{4}-W(\d{2})$/.exec(key);
  if (match) return `W${Number(match[1])}`;
  match = /^\d{4}-Q([1-4])$/.exec(key);
  if (match) return `Q${match[1]}`;
  match = /^\d{4}-(\d{2})-(\d{2})$/.exec(key);
  if (match) return `${Number(match[1])}/${Number(match[2])}`;
  match = /^\d{4}-(\d{2})$/.exec(key);
  if (match) return `${Number(match[1])}월`;
  return key;
}

export function changePercent(count: number, previous: number): number | null {
  return previous ? Math.round(((count - previous) / previous) * 100) : null;
}

export function formatChange(change: number | null): string {
  if (change === null) return "–";
  const rounded = Math.round(change);
  if (rounded === 0) return "±0%";
  return `${rounded > 0 ? "▲" : "▼"}${Math.abs(rounded)}%`;
}

export function formatZ(z: number): string {
  return `${z > 0 ? "+" : z < 0 ? "−" : "±"}${Math.abs(z).toFixed(1)}σ`;
}

export function formatPoints(delta: number): string {
  const rounded = Math.round(delta * 10) / 10;
  if (rounded === 0) return "±0%p";
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(1)}%p`;
}

export function last<T>(values: T[]): T {
  return values[values.length - 1];
}

export function mean(values: number[]): number {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}

export function sumMix(mix: TrackMix): number {
  return mix.news + mix.community + mix.research_ip + mix.oss;
}

/** Research + open source share of a track mix (0–1), null when empty. */
export function researchShare(mix: TrackMix): number | null {
  const total = sumMix(mix);
  return total ? (mix.research_ip + mix.oss) / total : null;
}

export type Stage = "research" | "diffusion" | "market";
export const STAGE_META: Record<Stage, { label: string; hint: string }> = {
  research: { label: "연구 주도", hint: "논문·오픈소스가 절반 이상: 초기 신호" },
  diffusion: { label: "확산", hint: "연구와 시장 언급이 섞임" },
  market: { label: "시장 주도", hint: "뉴스·커뮤니티가 80% 이상: 상용화·화제 단계" },
};

export function stageOf(share: number | null): Stage | null {
  if (share === null) return null;
  return share >= 0.5 ? "research" : share >= 0.2 ? "diffusion" : "market";
}

export type Quadrant = "leading" | "emerging" | "mainstream" | "niche";
export const QUADRANT_META: Record<Quadrant, { label: string; hint: string }> = {
  leading: { label: "주도", hint: "많이 언급되고 더 늘고 있음: 지금 대응" },
  emerging: { label: "부상", hint: "아직 적지만 빠르게 늘고 있음: 선점 타이밍" },
  mainstream: { label: "정착", hint: "많이 언급되지만 성장 둔화: 표준·경쟁 관리" },
  niche: { label: "잠복", hint: "적고 정체: 주기적 관찰" },
};
export const MOMENTUM_Z = 1;

export function volumeSplit(topics: Topic[]): number {
  const counts = topics.map((t) => last(t.counts)).filter((c) => c > 0).sort((a, b) => a - b);
  if (!counts.length) return 1;
  return Math.max(2, counts[Math.floor(counts.length / 2)]);
}

export function quadrantOf(topic: Topic, split: number): Quadrant {
  const big = last(topic.counts) >= split;
  const up = topic.z >= MOMENTUM_Z;
  return big ? (up ? "leading" : "mainstream") : up ? "emerging" : "niche";
}

/** Fill strength for a z-score on the diverging heat/cool scale (0–80 %). */
export function zLevel(z: number): number {
  return Math.round(Math.min(Math.abs(z) / 3, 1) * 80);
}

// ── layouts ──────────────────────────────────────────────────────────────────────────────

export type Rect = { x: number; y: number; w: number; h: number };

/** Squarified treemap (Bruls et al.): areas ∝ value, aspect ratios near 1. */
export function squarify<T extends { value: number }>(items: T[], box: Rect): (T & Rect)[] {
  const positive = items.filter((item) => item.value > 0).sort((a, b) => b.value - a.value);
  const total = positive.reduce((sum, item) => sum + item.value, 0);
  if (!total || box.w <= 0 || box.h <= 0) return [];
  const scale = (box.w * box.h) / total;
  const nodes = positive.map((item) => ({ item, area: item.value * scale }));
  const out: (T & Rect)[] = [];
  const rect = { ...box };
  const worst = (row: typeof nodes, side: number) => {
    const s = row.reduce((sum, n) => sum + n.area, 0);
    const max = Math.max(...row.map((n) => n.area));
    const min = Math.min(...row.map((n) => n.area));
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
  };
  const place = (row: typeof nodes) => {
    const s = row.reduce((sum, n) => sum + n.area, 0);
    if (rect.w >= rect.h) {
      const width = s / rect.h;
      let y = rect.y;
      for (const n of row) {
        const h = n.area / width;
        out.push({ ...n.item, x: rect.x, y, w: width, h });
        y += h;
      }
      rect.x += width;
      rect.w -= width;
    } else {
      const height = s / rect.w;
      let x = rect.x;
      for (const n of row) {
        const w = n.area / height;
        out.push({ ...n.item, x, y: rect.y, w, h: height });
        x += w;
      }
      rect.y += height;
      rect.h -= height;
    }
  };
  let row: typeof nodes = [];
  for (let i = 0; i < nodes.length; ) {
    const side = Math.min(rect.w, rect.h);
    if (!row.length || worst([...row, nodes[i]], side) <= worst(row, side)) {
      row.push(nodes[i]);
      i += 1;
    } else {
      place(row);
      row = [];
    }
  }
  if (row.length) place(row);
  return out;
}

/** Rough rendered width: Hangul/CJK ≈ 0.95em, capitals 0.66em, the rest 0.55em. */
export function textWidth(text: string, size: number): number {
  let em = 0;
  for (const char of text) {
    if (/[ᄀ-ᇿ぀-ヿ㄰-㆏一-鿿가-힯]/.test(char)) em += 0.95;
    else if (char === " ") em += 0.3;
    else if (/[A-Z0-9]/.test(char)) em += 0.66;
    else em += 0.55;
  }
  return em * size;
}

export type CloudWord = { key: string; text: string; weight: number };
export type PlacedWord = CloudWord & { x: number; y: number; size: number; w: number; h: number };

/** Archimedean-spiral word cloud, biggest words first; words that cannot fit are dropped. */
export function wordCloud(words: CloudWord[], width: number, height: number, minSize = 12, maxSize = 40): PlacedWord[] {
  const sorted = [...words].sort((a, b) => b.weight - a.weight || a.key.localeCompare(b.key));
  if (!sorted.length) return [];
  const hi = sorted[0].weight;
  const lo = sorted[sorted.length - 1].weight;
  const placed: PlacedWord[] = [];
  const pad = 3;
  const aspect = width / height;
  for (const word of sorted) {
    const size = Math.round(minSize + (maxSize - minSize) * Math.sqrt(hi === lo ? 1 : (word.weight - lo) / (hi - lo)));
    const w = textWidth(word.text, size) + pad;
    const h = size * 1.1 + pad;
    for (let step = 0; step < 1800; step += 1) {
      const angle = step * 0.32;
      const radius = 1.6 * angle;
      const x = width / 2 + radius * Math.cos(angle) * aspect * 0.8;
      const y = height / 2 + radius * Math.sin(angle) * 0.8;
      if (x - w / 2 < 0 || x + w / 2 > width || y - h / 2 < 0 || y + h / 2 > height) continue;
      const hit = placed.some((p) => Math.abs(p.x - x) * 2 < p.w + w && Math.abs(p.y - y) * 2 < p.h + h);
      if (!hit) {
        placed.push({ ...word, x, y, size, w, h });
        break;
      }
    }
  }
  return placed;
}

export type Edge = { a: string; b: string; weight: number };

/**
 * Deterministic Fruchterman–Reingold: short-range repulsion (so separate clusters do not push each
 * other into the walls), spring attraction along edges and an elliptical pull to the centre.
 */
export function forceLayout(nodes: string[], edges: Edge[], width: number, height: number, margin = 24, iterations = 400) {
  const n = nodes.length;
  const pos = new Map<string, { x: number; y: number }>();
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(n, 1);
    pos.set(node, { x: width / 2 + (width / 3) * Math.cos(angle), y: height / 2 + (height / 3) * Math.sin(angle) });
  });
  if (n < 2) return pos;
  const k = Math.sqrt(((width - 2 * margin) * (height - 2 * margin)) / n) * 0.85;
  const maxWeight = Math.max(...edges.map((e) => e.weight), 1);
  const sy = width / height;
  for (let iter = 0; iter < iterations; iter += 1) {
    const temperature = (width / 10) * (1 - iter / iterations) + 0.3;
    const shift = new Map(nodes.map((node) => [node, { x: 0, y: 0 }]));
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        const a = pos.get(nodes[i])!, b = pos.get(nodes[j])!;
        const dx = a.x - b.x || 0.01 * (i - j), dy = a.y - b.y || 0.01;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        if (d > 2.5 * k) continue;
        const f = (k * k) / d;
        shift.get(nodes[i])!.x += (dx / d) * f;
        shift.get(nodes[i])!.y += (dy / d) * f;
        shift.get(nodes[j])!.x -= (dx / d) * f;
        shift.get(nodes[j])!.y -= (dy / d) * f;
      }
    }
    for (const edge of edges) {
      const a = pos.get(edge.a), b = pos.get(edge.b);
      if (!a || !b) continue;
      const dx = a.x - b.x, dy = a.y - b.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = ((d * d) / k) * (0.6 + edge.weight / maxWeight);
      shift.get(edge.a)!.x -= (dx / d) * f;
      shift.get(edge.a)!.y -= (dy / d) * f;
      shift.get(edge.b)!.x += (dx / d) * f;
      shift.get(edge.b)!.y += (dy / d) * f;
    }
    for (const node of nodes) {
      const p = pos.get(node)!, s = shift.get(node)!;
      const gx = width / 2 - p.x, gy = (height / 2 - p.y) * sy;
      const g = Math.hypot(gx, gy);
      s.x += (gx / Math.max(g, 0.01)) * ((g * g) / k) * 0.05;
      s.y += ((gy / Math.max(g, 0.01)) * ((g * g) / k) * 0.05) / sy;
      const d = Math.max(Math.hypot(s.x, s.y), 0.01);
      p.x = Math.min(width - margin, Math.max(margin, p.x + (s.x / d) * Math.min(d, temperature)));
      p.y = Math.min(height - margin, Math.max(margin, p.y + (s.y / d) * Math.min(d, temperature)));
    }
  }
  return pos;
}

// ── data shaping ─────────────────────────────────────────────────────────────────────────

/** Share of voice per window for one field (0–100), from the radar's per-window totals. */
export function shareSeries(topic: Topic, totals: number[]): number[] {
  return topic.counts.map((count, i) => (totals[i] ? (count / totals[i]) * 100 : 0));
}

export function keywordIndex(radar: Radar): Map<string, Topic> {
  return new Map(radar.keywords.map((keyword) => [keyword.key, keyword]));
}

/** The topic to open first: the requested one, else the theme with the strongest momentum. */
export function initialFocus(radar: Radar, requested: Focus | null): Focus | null {
  if (requested) return requested;
  const ranked = [...radar.themes]
    .filter((t) => last(t.counts) > 0)
    .sort((a, b) => b.z - a.z || last(b.counts) - last(a.counts));
  if (ranked.length) return { kind: "theme", key: ranked[0].key };
  return radar.fields.length ? { kind: "field", key: radar.fields[0].key } : null;
}

// ── regions, ranks, projection ───────────────────────────────────────────────────────────

export const REGIONS: Region[] = ["kr", "global_en", "jp", "greater_china", "eu_other"];

/** Reports per region in the window: every item has one field, so field totals are item totals. */
export function regionTotals(radar: Radar): Record<Region, number> {
  const totals = Object.fromEntries(REGIONS.map((r) => [r, 0])) as Record<Region, number>;
  for (const field of radar.fields) for (const r of REGIONS) totals[r] += field.regions[r] ?? 0;
  return totals;
}

/**
 * Location quotient: the topic's share of one region's coverage over its share of all coverage.
 * 1 = in line, 2 = that region talks about it twice as much, 0.5 = half. Null when the region
 * would be expected to carry fewer than MIN_EXPECTED reports anyway: a zero there is not a gap.
 */
export const MIN_EXPECTED = 1.5;

export function specialization(topic: Topic, region: Region, totals: Record<Region, number>): number | null {
  const all = REGIONS.reduce((sum, r) => sum + totals[r], 0);
  const count = last(topic.counts);
  if (!totals[region] || !all || !count || (count * totals[region]) / all < MIN_EXPECTED) return null;
  return (topic.regions[region] / totals[region]) / (count / all);
}

const DAY = 86_400_000;

/** Days between the first report anywhere and the first Korean report; null when either is missing. */
export function koreaLagDays(topic: Topic): number | null {
  const kr = topic.first_seen.kr;
  const others = REGIONS.filter((r) => r !== "kr")
    .map((r) => topic.first_seen[r])
    .filter((t): t is string => !!t)
    .map((t) => Date.parse(t));
  if (!kr || !others.length) return null;
  return (Date.parse(kr) - Math.min(...others)) / DAY;
}

/** Technologies with real coverage abroad this period and none from Korean sources. */
export function koreaGaps(radar: Radar, limit = 6): Topic[] {
  return radar.keywords
    .filter((k) => k.state !== "falling" && k.regions.kr === 0 && last(k.counts) >= 4)
    .sort((a, b) => last(b.counts) - last(a.counts) || b.z - a.z)
    .slice(0, limit);
}

/** Current-window count at the pace so far; null for a closed window or too early to tell. */
export function projected(count: number, elapsed: number | null): number | null {
  if (elapsed === null || elapsed >= 1 || elapsed < 0.15) return null;
  return Math.round(count / elapsed);
}

/** Rank (1 = most mentioned) of each topic in every window, for the `top` topics of the last window. */
export function rankSeries(topics: Topic[], top = 10): { topic: Topic; ranks: (number | null)[] }[] {
  const windows = topics[0]?.counts.length ?? 0;
  const ranksByWindow = Array.from({ length: windows }, (_, i) => {
    const ordered = topics.filter((t) => t.counts[i] > 0).sort((a, b) => b.counts[i] - a.counts[i] || a.key.localeCompare(b.key));
    return new Map(ordered.map((t, rank) => [t.key, rank + 1]));
  });
  return [...topics]
    .filter((t) => last(t.counts) > 0)
    .sort((a, b) => last(b.counts) - last(a.counts) || a.key.localeCompare(b.key))
    .slice(0, top)
    .map((topic) => ({ topic, ranks: ranksByWindow.map((ranks) => ranks.get(topic.key) ?? null) }));
}

/** Net opportunity: (opportunity − risk) ÷ all classified reports, −1…1. */
export function netOpportunity(topic: Topic): number | null {
  const { opportunity, risk, watch } = topic.impacts;
  const total = opportunity + risk + watch;
  return total ? (opportunity - risk) / total : null;
}
