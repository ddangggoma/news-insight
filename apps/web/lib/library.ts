// Bookmarks and read marks, kept only in this browser (requirements §9), with a versioned
// JSON export/import so readers can move them between devices.

export const LIBRARY_KEY = "ni.library";
export const LIBRARY_VERSION = 1;
const MAX_READ = 5000;

export interface SavedItem {
  id: number;
  title: string;
  url: string;
  source_name: string;
  saved_at: string;
}

export interface Library {
  version: typeof LIBRARY_VERSION;
  bookmarks: Record<string, SavedItem>;
  read: Record<string, string>;
}

export const EMPTY_LIBRARY: Library = Object.freeze({ version: LIBRARY_VERSION, bookmarks: {}, read: {} }) as Library;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function validItem(value: unknown): value is SavedItem {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    typeof value.title === "string" &&
    typeof value.url === "string" &&
    /^https?:\/\//.test(value.url) &&
    typeof value.source_name === "string" &&
    typeof value.saved_at === "string"
  );
}

/** A Library from untrusted JSON (storage or an imported file), or null if unusable. */
export function parseLibrary(value: unknown): Library | null {
  if (!isRecord(value) || value.version !== LIBRARY_VERSION) return null;
  const bookmarks: Record<string, SavedItem> = {};
  if (isRecord(value.bookmarks)) {
    for (const item of Object.values(value.bookmarks)) {
      if (validItem(item)) bookmarks[String(item.id)] = item;
    }
  }
  const read: Record<string, string> = {};
  if (isRecord(value.read)) {
    for (const [id, at] of Object.entries(value.read)) {
      if (/^\d+$/.test(id) && typeof at === "string") read[id] = at;
    }
  }
  return { version: LIBRARY_VERSION, bookmarks, read };
}

function trimRead(read: Record<string, string>): Record<string, string> {
  const entries = Object.entries(read);
  if (entries.length <= MAX_READ) return read;
  return Object.fromEntries(entries.sort((a, b) => b[1].localeCompare(a[1])).slice(0, MAX_READ));
}

export function mergeLibraries(base: Library, incoming: Library): Library {
  const read = { ...base.read };
  for (const [id, at] of Object.entries(incoming.read)) {
    if (!read[id] || read[id] < at) read[id] = at;
  }
  return { version: LIBRARY_VERSION, bookmarks: { ...base.bookmarks, ...incoming.bookmarks }, read: trimRead(read) };
}

export function toggleBookmark(library: Library, item: Omit<SavedItem, "saved_at">, now: Date): Library {
  const key = String(item.id);
  const bookmarks = { ...library.bookmarks };
  if (bookmarks[key]) delete bookmarks[key];
  else bookmarks[key] = { ...item, saved_at: now.toISOString() };
  return { ...library, bookmarks };
}

export function setRead(library: Library, id: number, read: boolean, now: Date): Library {
  const next = { ...library.read };
  if (read) next[String(id)] = now.toISOString();
  else delete next[String(id)];
  return { ...library, read: trimRead(next) };
}

export function exportLibrary(library: Library, now: Date): string {
  return JSON.stringify({ ...library, exported_at: now.toISOString() }, null, 2);
}

// --- browser store (useSyncExternalStore) ---

let cachedRaw: string | null | undefined;
let cached: Library = EMPTY_LIBRARY;
const listeners = new Set<() => void>();

export function readLibrary(): Library {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(LIBRARY_KEY);
  } catch {
    return cached;
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      cached = (raw && parseLibrary(JSON.parse(raw))) || EMPTY_LIBRARY;
    } catch {
      cached = EMPTY_LIBRARY;
    }
  }
  return cached;
}

export function writeLibrary(library: Library): void {
  try {
    window.localStorage.setItem(LIBRARY_KEY, JSON.stringify(library));
  } catch {
    cached = library; // storage unavailable: keep it for this page view
    cachedRaw = undefined;
  }
  listeners.forEach((listener) => listener());
}

export function subscribeLibrary(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === LIBRARY_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}
