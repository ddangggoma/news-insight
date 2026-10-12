// Shared by proxy.ts and server code, so no "server-only" here: nothing in this file runs in the browser.

// Identical requests already on their way share one answer (2026-10-12). A burst of reloads or
// several users opening the same page used to send the API one copy of each call per request;
// the API then queued them all behind one database pool. On globalThis so proxy.ts and server
// components share it in the standalone server.
const flights: Map<string, Promise<unknown>> = ((globalThis as { __niFlights?: Map<string, Promise<unknown>> })
  .__niFlights ??= new Map());

/** Run `work` once per key at a time; callers that arrive meanwhile await the same promise. */
export function singleFlight<T>(key: string, work: () => Promise<T>): Promise<T> {
  const running = flights.get(key);
  if (running) return running as Promise<T>;
  const flight = work().finally(() => {
    if (flights.get(key) === flight) flights.delete(key);
  });
  flights.set(key, flight);
  return flight;
}

/** Requests in flight right now (tests). */
export function flightCount(): number {
  return flights.size;
}
