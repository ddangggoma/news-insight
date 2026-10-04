import { describe, expect, it } from "vitest";

import { EMPTY_LIBRARY, exportLibrary, mergeLibraries, parseLibrary, setRead, toggleBookmark } from "@/lib/library";

const NOW = new Date("2026-10-05T00:00:00Z");
const ITEM = { id: 7, title: "삼성, 갤럭시 S30 공개", url: "https://example.com/s30", source_name: "The Verge" };

describe("library", () => {
  it("toggles bookmarks and read marks without mutating", () => {
    const saved = toggleBookmark(EMPTY_LIBRARY, ITEM, NOW);
    const read = setRead(saved, 7, true, NOW);

    expect(EMPTY_LIBRARY.bookmarks).toEqual({});
    expect(saved.bookmarks["7"]).toMatchObject({ ...ITEM, saved_at: NOW.toISOString() });
    expect(read.read["7"]).toBe(NOW.toISOString());
    expect(toggleBookmark(read, ITEM, NOW).bookmarks).toEqual({});
    expect(setRead(read, 7, false, NOW).read).toEqual({});
  });

  it("round-trips the versioned export", () => {
    const library = setRead(toggleBookmark(EMPTY_LIBRARY, ITEM, NOW), 9, true, NOW);
    const parsed = parseLibrary(JSON.parse(exportLibrary(library, NOW)));

    expect(parsed).toEqual(library);
  });

  it("rejects other versions and drops unsafe entries", () => {
    expect(parseLibrary({ version: 2, bookmarks: {}, read: {} })).toBeNull();
    expect(parseLibrary("nope")).toBeNull();
    const parsed = parseLibrary({
      version: 1,
      bookmarks: {
        a: { ...ITEM, saved_at: "x" },
        b: { ...ITEM, id: 8, url: "javascript:alert(1)", saved_at: "x" },
      },
      read: { "7": "t", evil: "t", "8": 3 },
    });

    expect(Object.keys(parsed?.bookmarks ?? {})).toEqual(["7"]);
    expect(parsed?.read).toEqual({ "7": "t" });
  });

  it("merges keeping the newest read time", () => {
    const a = { ...EMPTY_LIBRARY, read: { "1": "2026-10-01", "2": "2026-10-03" } };
    const b = { ...toggleBookmark(EMPTY_LIBRARY, ITEM, NOW), read: { "1": "2026-10-02", "2": "2026-10-02" } };

    const merged = mergeLibraries(a, b);

    expect(merged.read).toEqual({ "1": "2026-10-02", "2": "2026-10-03" });
    expect(Object.keys(merged.bookmarks)).toEqual(["7"]);
  });
});
