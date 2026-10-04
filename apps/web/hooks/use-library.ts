"use client";

import { useCallback, useSyncExternalStore } from "react";

import {
  EMPTY_LIBRARY,
  type Library,
  readLibrary,
  setRead,
  subscribeLibrary,
  toggleBookmark,
  writeLibrary,
} from "@/lib/library";

export function useLibrary() {
  const library = useSyncExternalStore(subscribeLibrary, readLibrary, () => EMPTY_LIBRARY);
  const update = useCallback((change: (current: Library) => Library) => writeLibrary(change(readLibrary())), []);
  return {
    library,
    update,
    toggleBookmark: (item: Parameters<typeof toggleBookmark>[1]) => update((l) => toggleBookmark(l, item, new Date())),
    markRead: (id: number, read = true) => update((l) => setRead(l, id, read, new Date())),
  };
}
