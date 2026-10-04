import type { Cell, Radar, RadarKind } from "@/lib/reader-types";
import { BUSINESS_LABEL, FIELD_LABEL } from "@/lib/taxonomy";

export const RADAR_KINDS: Record<RadarKind, string> = { day: "일간", week: "주간", month: "월간", quarter: "분기" };
export const NO_BUSINESS = "none";
export const BUSINESS_COLUMNS = [...Object.keys(BUSINESS_LABEL), NO_BUSINESS];

export function businessLabel(key: string): string {
  return key === NO_BUSINESS ? "사업부 미지정" : (BUSINESS_LABEL[key] ?? key);
}

export function shortBusiness(key: string): string {
  return key === NO_BUSINESS ? "미지정" : businessLabel(key).split(" · ")[0];
}

export function isRadarKind(value: string): value is RadarKind {
  return value in RADAR_KINDS;
}

/** Cell fill strength (0–92 %). Square root keeps small counts visible next to one huge cell. */
export function heatLevel(count: number, max: number): number {
  return max > 0 && count > 0 ? Math.max(8, Math.round(Math.sqrt(count / max) * 92)) : 0;
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

export type CellRef = { field: string; business: string };

export function parseCell(value: string | undefined): CellRef | null {
  if (!value) return null;
  const [field, business] = value.split(".");
  return field in FIELD_LABEL && BUSINESS_COLUMNS.includes(business) ? { field, business } : null;
}

/** Rows are fields by current volume; `limit` keeps the busiest ones. */
export function heatRows(radar: Radar, limit?: number): string[] {
  const totals = new Map<string, number>();
  for (const cell of radar.cells) totals.set(cell.field, (totals.get(cell.field) ?? 0) + cell.count);
  const ordered = Object.keys(FIELD_LABEL).sort(
    (a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0) || FIELD_LABEL[a].localeCompare(FIELD_LABEL[b], "ko"),
  );
  return limit ? ordered.slice(0, limit) : ordered;
}

export function cellIndex(cells: Cell[]): Map<string, Cell> {
  return new Map(cells.map((cell) => [`${cell.field}.${cell.business}`, cell]));
}

/** The cell to open first: the requested one, else the hottest, else the busiest. */
export function initialCell(radar: Radar, requested: CellRef | null): CellRef | null {
  if (requested) return requested;
  if (radar.kpis.hottest) return { field: radar.kpis.hottest.field, business: radar.kpis.hottest.business };
  const busiest = [...radar.cells].sort((a, b) => b.count - a.count)[0];
  return busiest && busiest.count ? { field: busiest.field, business: busiest.business } : null;
}
