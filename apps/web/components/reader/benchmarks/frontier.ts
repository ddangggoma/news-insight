/**
 * The efficiency frontier: walking from the cheapest point up, the points that score higher
 * than every cheaper one. Ties on x keep only the best y. Non-finite points never qualify.
 */
export function paretoFrontier(points: { x: number; y: number; id: string }[]): string[] {
  const sorted = points
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
    .slice()
    .sort((a, b) => a.x - b.x || b.y - a.y);
  const ids: string[] = [];
  let best = -Infinity;
  for (const point of sorted) {
    if (point.y > best) {
      ids.push(point.id);
      best = point.y;
    }
  }
  return ids;
}
