import { readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PAGE_VIEW_PATH,
  ROUTE_HANDLERS,
  accessKind,
  cleanQuery,
  clearAccessLog,
  flushAccessLog,
  forwardedIp,
  pendingAccess,
  recordAccess,
} from "@/lib/access-log";
import { describeAgent } from "@/lib/access-types";
import { clearSessionCache } from "@/lib/auth";
import { formatStamp } from "@/lib/format";
import { proxy } from "@/proxy";

const page = { user_id: 2, kind: "page", method: "GET", path: "/radar" } as const;

afterEach(() => {
  clearAccessLog();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

/** "/radar/x1/x1/topic" for app/(reader)/radar/[period]/[key]/topic/route.ts */
function sampleUrl(file: string): string {
  const parts = relative("app", file).split(sep).slice(0, -1);
  return `/${parts
    .filter((part) => !/^\(.*\)$/.test(part))
    .map((part) => (part.startsWith("[...") ? "a/b" : part.startsWith("[") ? "x1" : part))
    .join("/")}`;
}

function routeFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return routeFiles(path);
    return entry.name === "route.ts" ? [path] : [];
  });
}

describe("accessKind", () => {
  it("notes server actions on any page", () => {
    expect(accessKind(new Headers({ "next-action": "7f3a" }), "/console/users")).toBe("action");
  });

  it.each(["/export/briefings/2026-10-17.pdf", "/console/review/export", "/radar/week/2026-W42/topic", "/reports/7/view"])(
    "notes the route handler %s",
    (path) => {
      expect(accessKind(new Headers({ accept: "*/*" }), path)).toBe("api");
    },
  );

  it.each(["/", "/radar/week/2026-W42", "/reports/7", "/console/users"])(
    "leaves the page %s to the browser's report (the proxy cannot tell it from a prefetch)",
    (path) => {
      expect(accessKind(new Headers({ "sec-fetch-dest": "document" }), path)).toBeNull();
    },
  );

  it("knows every route handler a browser calls", () => {
    const browserRoutes = routeFiles("app")
      .map(sampleUrl)
      .filter((url) => !url.startsWith("/internal/") && url !== PAGE_VIEW_PATH);
    expect(browserRoutes.length).toBeGreaterThanOrEqual(5);
    for (const url of browserRoutes) {
      expect(ROUTE_HANDLERS.some((pattern) => pattern.test(url)), url).toBe(true);
    }
  });
});

describe("request details", () => {
  it("keeps the first forwarded address", () => {
    expect(forwardedIp(new Headers({ "x-forwarded-for": "203.0.113.7, 172.18.0.5" }))).toBe("203.0.113.7");
    expect(forwardedIp(new Headers())).toBeUndefined();
  });

  it("drops the RSC cache buster from the query", () => {
    expect(cleanQuery(new URLSearchParams("_rsc=abc&scope=dx"))).toBe("scope=dx");
    expect(cleanQuery(new URLSearchParams("_rsc=abc"))).toBeUndefined();
  });
});

describe("recordAccess", () => {
  it("counts a page shown twice within 5 seconds once, but every action", () => {
    recordAccess(page, 0);
    recordAccess(page, 3_000);
    recordAccess({ ...page, query: "period=week" }, 3_000);
    recordAccess(page, 6_000);
    recordAccess({ ...page, kind: "action", method: "POST" }, 6_000);
    recordAccess({ ...page, kind: "action", method: "POST" }, 6_001);

    expect(pendingAccess().map((e) => [e.kind, e.query ?? "", e.at])).toEqual([
      ["page", "", "1970-01-01T00:00:00.000Z"],
      ["page", "period=week", "1970-01-01T00:00:03.000Z"],
      ["page", "", "1970-01-01T00:00:06.000Z"],
      ["action", "", "1970-01-01T00:00:06.000Z"],
      ["action", "", "1970-01-01T00:00:06.001Z"],
    ]);
  });

  it("counts a route the page polls once every 30 seconds", () => {
    const route = { ...page, kind: "api", path: "/radar/week/2026-W42/topic" } as const;
    recordAccess(route, 0);
    recordAccess(route, 20_000);
    recordAccess(route, 31_000);
    expect(pendingAccess()).toHaveLength(2);
  });

  it("counts one briefing play, not each range request", () => {
    const play = { ...page, kind: "media", path: "/media/briefings/2026-10-17-v1.m4a" } as const;
    recordAccess(play, 0);
    recordAccess(play, 60_000);
    expect(pendingAccess()).toHaveLength(1);
  });
});

describe("flushAccessLog", () => {
  it("sends the waiting entries in batches the API accepts, with the console key", async () => {
    vi.stubEnv("CONSOLE_API_KEY", "test-key");
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    for (let i = 0; i < 501; i += 1) recordAccess({ ...page, kind: "action", method: "POST" }, i);

    await flushAccessLog();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/admin\/access-log$/);
    expect((init.headers as Record<string, string>)["X-Console-Key"]).toBe("test-key");
    expect(JSON.parse(String(init.body)).entries).toHaveLength(500);
    expect(pendingAccess()).toHaveLength(0);
  });

  it("drops a batch the API cannot take instead of throwing", async () => {
    vi.stubEnv("CONSOLE_API_KEY", "test-key");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    recordAccess(page, 0);

    await expect(flushAccessLog()).resolves.toBeUndefined();

    expect(pendingAccess()).toHaveLength(0);
    expect(warn).toHaveBeenCalledWith(expect.stringMatching(/1 entries not sent/));
    warn.mockRestore();
  });
});

describe("proxy access log", () => {
  const reader = { id: 2, username: "reader.one", name: "김독자", role: "reader", must_change_password: false };

  beforeEach(() => {
    clearSessionCache();
    vi.stubEnv("CONSOLE_API_KEY", "test-key");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(reader), { status: 200 })));
  });

  function request(path: string, headers: Record<string, string> = {}, method = "GET"): NextRequest {
    return new NextRequest(`http://localhost:8713${path}`, {
      method,
      headers: { cookie: "ni_session=live", "x-forwarded-for": "203.0.113.7", ...headers },
    });
  }

  it("notes a server action with who and from where", async () => {
    await proxy(request("/console/users?status=pending", { "next-action": "7f3a" }, "POST"));

    expect(pendingAccess()).toEqual([
      expect.objectContaining({ user_id: 2, kind: "action", method: "POST", path: "/console/users", query: "status=pending", ip: "203.0.113.7" }),
    ]);
  });

  it("notes route calls, even refused ones, and leaves pages to the browser", async () => {
    await proxy(request("/radar/week/2026-W42/companies?scope=relevant"));
    await proxy(request("/console/review/export"));
    await proxy(request("/briefings", { "sec-fetch-dest": "document" }));

    expect(pendingAccess().map((e) => [e.kind, e.path])).toEqual([
      ["api", "/radar/week/2026-W42/companies"],
      ["api", "/console/review/export"],
    ]);
  });

  it("notes nothing without a session", async () => {
    await proxy(new NextRequest("http://localhost:8713/export/briefings/2026-10-17.pdf"));
    expect(pendingAccess()).toHaveLength(0);
  });
});

describe("console display", () => {
  it.each([
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36", "Chrome 141 · macOS"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1", "Safari 18 · iPhone"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0", "Edge 141 · Windows"],
    ["Firefox", "Firefox"],
    [null, ""],
  ])("names the browser of %s", (agent, label) => {
    expect(describeAgent(agent)).toBe(label);
  });

  it("stamps log times in KST with seconds", () => {
    expect(formatStamp("2026-10-17T02:26:38.950Z")).toBe("10.17 11:26:38");
  });
});
