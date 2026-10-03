export type SearchParams = Record<string, string | string[] | undefined>;

export function param(searchParams: SearchParams, name: string): string | undefined {
  const raw = searchParams[name];
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value && value !== "all" ? value : undefined;
}

export function pageParam(searchParams: SearchParams): number {
  const value = Number.parseInt(param(searchParams, "page") ?? "1", 10);
  return Number.isFinite(value) && value > 0 ? value : 1;
}
