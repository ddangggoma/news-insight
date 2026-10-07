import "server-only";

import { type QueryValue, withQuery } from "@/lib/query";

const BASE_URL = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8711";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type Headers = Record<string, string>;

async function send(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  extra: Headers = {},
): Promise<Response> {
  const key = process.env.CONSOLE_API_KEY;
  if (!key) throw new ApiError(503, "CONSOLE_API_KEY is not configured for the web server");
  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { ...extra, "X-Console-Key": key, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, (await response.text()) || response.statusText);
  }
  return response;
}

async function request<T>(method: "GET" | "POST" | "PATCH", path: string, body?: unknown, extra?: Headers): Promise<T> {
  const response = await send(method, path, body, extra);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, QueryValue>, headers?: Headers) =>
    request<T>("GET", withQuery(path, params), undefined, headers),
  post: <T>(path: string, body?: unknown, headers?: Headers) => request<T>("POST", path, body, headers),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  text: async (path: string) => (await send("GET", path)).text(),
  delete: async (path: string): Promise<void> => {
    await send("DELETE", path);
  },
};
