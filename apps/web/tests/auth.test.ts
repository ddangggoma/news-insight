// Next 16.3 ships the docs' unstable_doesProxyMatch under its old name
import { unstable_doesMiddlewareMatch as doesProxyMatch } from "next/experimental/testing/server";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSessionCache, safeNext } from "@/lib/auth";
import { config, proxy } from "@/proxy";

describe("safeNext", () => {
  it("keeps same-site paths with their query", () => {
    expect(safeNext("/radar/week/2026-W40?focus=ai")).toBe("/radar/week/2026-W40?focus=ai");
    expect(safeNext("/console/users")).toBe("/console/users");
  });

  it.each([
    ["absolute URL", "https://evil.example/"],
    ["protocol-relative", "//evil.example"],
    ["backslash", "/\\evil.example"],
    ["control character", "/a\nb"],
    ["empty", ""],
    ["not a string", null],
    ["login loop", "/login?next=/"],
    ["sign-up", "/signup"],
  ])("falls back to / for %s", (_, value) => {
    expect(safeNext(value)).toBe("/");
  });
});

describe("proxy matcher", () => {
  it.each(["/", "/radar", "/items/42", "/console/users", "/account", "/change-password", "/feed.xml"])(
    "guards %s",
    (url) => {
      expect(doesProxyMatch({ config, url })).toBe(true);
    },
  );

  it.each(["/login", "/signup", "/_next/static/chunks/app.js", "/icon.svg", "/internal/revalidate"])(
    "leaves %s alone",
    (url) => {
      expect(doesProxyMatch({ config, url })).toBe(false);
    },
  );
});

const reader = { id: 2, username: "reader.one", name: "김독자", role: "reader", must_change_password: false };

function request(path: string, init: { cookie?: string; method?: string } = {}): NextRequest {
  return new NextRequest(`http://localhost:8713${path}`, {
    method: init.method ?? "GET",
    headers: init.cookie ? { cookie: `ni_session=${init.cookie}` } : {},
  });
}

describe("proxy", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    clearSessionCache();
    vi.stubEnv("CONSOLE_API_KEY", "test-key");
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  function answer(status: number, body: unknown = {}) {
    fetchMock.mockImplementation(async () => new Response(JSON.stringify(body), { status }));
  }

  it("sends visitors without a session to the login page, keeping where they were going", async () => {
    const response = await proxy(request("/radar?scope=dx"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:8713/login?next=%2Fradar%3Fscope%3Ddx");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("checks the session with the API and drops a dead cookie", async () => {
    answer(401);
    const response = await proxy(request("/", { cookie: "revoked" }));
    expect(response.headers.get("location")).toBe("http://localhost:8713/login");
    expect(response.headers.get("set-cookie")).toMatch(/ni_session=;/);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/admin\/accounts\/session$/);
    expect(JSON.parse(init.body)).toEqual({ token: "revoked" });
  });

  it("refuses server actions without a session instead of redirecting them", async () => {
    const response = await proxy(request("/console", { method: "POST" }));
    expect(response.status).toBe(401);
  });

  it("lets an active session through", async () => {
    answer(200, reader);
    const response = await proxy(request("/briefings", { cookie: "live" }));
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("keeps readers out of the console", async () => {
    answer(200, reader);
    const response = await proxy(request("/console/users", { cookie: "live" }));
    expect(response.headers.get("location")).toBe("http://localhost:8713/");
  });

  it("holds a temporary password at the change page", async () => {
    answer(200, { ...reader, must_change_password: true });
    const elsewhere = await proxy(request("/radar", { cookie: "temp" }));
    expect(elsewhere.headers.get("location")).toBe("http://localhost:8713/change-password");
    const there = await proxy(request("/change-password", { cookie: "temp" }));
    expect(there.headers.get("x-middleware-next")).toBe("1");
  });

  it("fails closed when the API cannot answer", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const response = await proxy(request("/", { cookie: "live" }));
    expect(response.status).toBe(503);
  });
});

describe("session cache", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("reuses a confirmed session briefly and forgets it on logout", async () => {
    const { forgetSession, lookupSession } = await import("@/lib/auth");
    clearSessionCache();
    vi.stubEnv("CONSOLE_API_KEY", "k");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 1, username: "a", role: "admin" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await lookupSession("tok");
    await lookupSession("tok");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    forgetSession("tok");
    await lookupSession("tok");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
