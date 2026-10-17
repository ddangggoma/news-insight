import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearAccessLog, pendingAccess } from "@/lib/access-log";

const session = vi.hoisted(() => ({ user: null as null | { id: number; must_change_password: boolean } }));
const location = vi.hoisted(() => ({ pathname: "/radar", search: "" }));

vi.mock("@/lib/session", () => ({ currentUser: async () => session.user }));
vi.mock("next/navigation", () => ({
  usePathname: () => location.pathname,
  useSearchParams: () => new URLSearchParams(location.search),
}));

const { POST } = await import("@/app/page-view/route");
const { PageViewBeacon } = await import("@/components/page-view-beacon");

function report(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost:8716/page-view", {
    method: "POST",
    body: typeof body === "string" ? body : JSON.stringify(body),
    headers: { "sec-fetch-site": "same-origin", "x-forwarded-for": "203.0.113.7", ...headers },
  });
}

afterEach(() => {
  clearAccessLog();
  vi.unstubAllGlobals();
  session.user = null;
});

describe("page-view route", () => {
  beforeEach(() => {
    session.user = { id: 2, must_change_password: false };
  });

  it("notes the page the browser shows, with the address", async () => {
    const response = await POST(report({ href: "/radar/week/2026-W42?scope=dx" }));

    expect(response.status).toBe(204);
    expect(pendingAccess()).toEqual([
      expect.objectContaining({ user_id: 2, kind: "page", method: "GET", path: "/radar/week/2026-W42", query: "scope=dx", ip: "203.0.113.7" }),
    ]);
  });

  it.each([
    ["an off-site address", { href: "//evil.example/x" }, 400],
    ["an absolute URL", { href: "https://evil.example/" }, 400],
    ["no address", {}, 400],
    ["broken JSON", "{", 400],
  ] as const)("ignores %s", async (_, body, status) => {
    expect((await POST(report(body))).status).toBe(status);
    expect(pendingAccess()).toHaveLength(0);
  });

  it("ignores reports from another site and from a held temporary password", async () => {
    expect((await POST(report({ href: "/" }, { "sec-fetch-site": "cross-site" }))).status).toBe(403);
    session.user = { id: 2, must_change_password: true };
    expect((await POST(report({ href: "/" }))).status).toBe(401);
    expect(pendingAccess()).toHaveLength(0);
  });
});

describe("PageViewBeacon", () => {
  it("reports the page it shows with its query", () => {
    const beacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });
    location.pathname = "/radar";
    location.search = "period=week";

    render(<PageViewBeacon />);

    expect(beacon).toHaveBeenCalledWith("/page-view", JSON.stringify({ href: "/radar?period=week" }));
  });

  it("stays quiet on the login page", () => {
    const beacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });
    location.pathname = "/login";
    location.search = "";

    render(<PageViewBeacon />);

    expect(beacon).not.toHaveBeenCalled();
  });
});
