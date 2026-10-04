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

async function send(method: "GET" | "POST" | "PATCH", path: string, body?: unknown): Promise<Response> {
  const key = process.env.CONSOLE_API_KEY;
  if (!key) throw new ApiError(503, "CONSOLE_API_KEY is not configured for the web server");
  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { "X-Console-Key": key, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, (await response.text()) || response.statusText);
  }
  return response;
}

async function request<T>(method: "GET" | "POST" | "PATCH", path: string, body?: unknown): Promise<T> {
  return (await (await send(method, path, body)).json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, QueryValue>) => request<T>("GET", withQuery(path, params)),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  text: async (path: string) => (await send("GET", path)).text(),
};
