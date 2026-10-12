import { afterEach, describe, expect, it, vi } from "vitest";

import { clearSessionCache, lookupSession } from "@/lib/auth";
import { flightCount, singleFlight } from "@/lib/single-flight";

describe("singleFlight", () => {
  it("shares one run between callers that arrive while it is in flight", async () => {
    let release!: (value: string) => void;
    const work = vi.fn(() => new Promise<string>((resolve) => (release = resolve)));

    const calls = [singleFlight("k", work), singleFlight("k", work), singleFlight("k", work)];
    release("done");

    expect(await Promise.all(calls)).toEqual(["done", "done", "done"]);
    expect(work).toHaveBeenCalledTimes(1);
    expect(flightCount()).toBe(0);
  });

  it("starts fresh after a run settles, including after a failure", async () => {
    await expect(singleFlight("k", () => Promise.reject(new Error("down")))).rejects.toThrow("down");
    expect(flightCount()).toBe(0);
    await expect(singleFlight("k", async () => "again")).resolves.toBe("again");
  });

  it("keeps different keys apart", async () => {
    const [a, b] = await Promise.all([singleFlight("a", async () => 1), singleFlight("b", async () => 2)]);
    expect([a, b]).toEqual([1, 2]);
  });
});

describe("lookupSession", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    clearSessionCache();
  });

  it("asks the API once for a burst of checks on one token", async () => {
    vi.stubEnv("CONSOLE_API_KEY", "console-key");
    const user = { id: 1, username: "reader", role: "reader" };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(user), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const users = await Promise.all(Array.from({ length: 10 }, () => lookupSession("token-1")));

    expect(users.every((found) => found?.id === 1)).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
