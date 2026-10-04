export type QueryValue = string | number | readonly string[] | undefined | null;

export function withQuery(path: string, params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === "all") continue;
    if (Array.isArray(value)) {
      for (const entry of value) if (entry) search.append(key, entry);
      continue;
    }
    search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function pageHref(pathname: string, params: Record<string, QueryValue>, page: number): string {
  const rest = Object.fromEntries(Object.entries(params).filter(([key]) => key !== "page"));
  return withQuery(pathname, { ...rest, page: page > 1 ? page : undefined });
}
