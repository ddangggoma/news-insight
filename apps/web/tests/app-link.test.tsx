import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppLink } from "@/components/app-link";
import { NavigationProgress } from "@/components/navigation-progress";
import { REPEAT_GUARD_MS, finishNavigation, isRepeat, pendingRoute, resetNavigation, routeOf, startNavigation } from "@/lib/navigation-state";

const navigation = vi.hoisted(() => ({ pathname: "/", search: "", pushed: [] as string[] }));
// jsdom gets the pages-router Link; this one follows the App Router's click contract
// (next/dist/client/app-dir/link.js: onNavigate first, and preventDefault cancels the push)
vi.mock("next/link", () => ({
  default: ({
    href,
    onNavigate,
    prefetch: _prefetch,
    ...rest
  }: {
    href: string;
    prefetch?: unknown;
    onNavigate?: (event: { preventDefault(): void }) => void;
  } & Record<string, unknown>) => (
    <a
      href={href}
      {...rest}
      onClick={(event) => {
        event.preventDefault();
        let cancelled = false;
        onNavigate?.({ preventDefault: () => (cancelled = true) });
        if (!cancelled) navigation.pushed.push(href);
      }}
    />
  ),
  useLinkStatus: () => ({ pending: false }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

afterEach(() => {
  act(() => resetNavigation());
  navigation.pushed.length = 0;
  vi.useRealTimers();
});

describe("routeOf", () => {
  it("keeps path and query, drops the hash", () => {
    expect(routeOf("/items/4?tab=team#notes", "http://localhost/")).toBe("/items/4?tab=team");
    expect(routeOf("?page=2", "http://localhost/radar")).toBe("/radar?page=2");
  });
});

describe("AppLink", () => {
  it("marks the page as loading on click and ignores a second click on the same link", () => {
    const onNavigate = vi.fn();
    render(
      <AppLink href="/items/4" onNavigate={onNavigate}>
        기사
      </AppLink>,
    );
    const link = screen.getByRole("link", { name: "기사" });

    fireEvent.click(link);
    expect(pendingRoute()).toBe("/items/4");
    fireEvent.click(link);

    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(navigation.pushed).toEqual(["/items/4"]);
  });

  it("lets a different link replace the one still loading", () => {
    render(
      <>
        <AppLink href="/radar">레이더</AppLink>
        <AppLink href="/deals">투자</AppLink>
      </>,
    );

    fireEvent.click(screen.getByRole("link", { name: "레이더" }));
    fireEvent.click(screen.getByRole("link", { name: "투자" }));

    expect(pendingRoute()).toBe("/deals");
    expect(navigation.pushed).toEqual(["/radar", "/deals"]);
  });

  it("opens a link to the page already open once, without waiting on a URL change", () => {
    render(<AppLink href="/">홈</AppLink>);
    const link = screen.getByRole("link", { name: "홈" });

    fireEvent.click(link);
    fireEvent.click(link);
    fireEvent.click(link);

    expect(pendingRoute()).toBeNull();
    expect(navigation.pushed).toEqual(["/"]);
  });

  it("ignores more clicks right after a fast navigation finished, then allows them again", () => {
    vi.useFakeTimers();
    render(<AppLink href="/patents">특허</AppLink>);
    const link = screen.getByRole("link", { name: "특허" });

    fireEvent.click(link);
    act(() => finishNavigation()); // the prefetched page opened at once
    fireEvent.click(link);
    expect(navigation.pushed).toEqual(["/patents"]);

    vi.advanceTimersByTime(REPEAT_GUARD_MS);
    fireEvent.click(link);
    expect(navigation.pushed).toEqual(["/patents", "/patents"]);
  });
});

describe("navigation state", () => {
  it("treats the same route as a repeat only for a short while", () => {
    startNavigation("/radar", { loading: false, now: 1_000 });
    expect(isRepeat("/radar", 1_000 + REPEAT_GUARD_MS - 1)).toBe(true);
    expect(isRepeat("/radar", 1_000 + REPEAT_GUARD_MS)).toBe(false);
    expect(isRepeat("/deals", 1_001)).toBe(false);
  });

  it("gives up after the timeout so links never stay blocked", () => {
    vi.useFakeTimers();
    startNavigation("/slow");
    vi.advanceTimersByTime(20_000);
    expect(pendingRoute()).toBeNull();
  });
});

describe("NavigationProgress", () => {
  it("shows while a navigation is pending and ends when the URL changes", () => {
    const { container, rerender } = render(<NavigationProgress />);
    const bar = container.querySelector(".navigation-progress");
    expect(bar).toHaveAttribute("data-active", "false");

    act(() => startNavigation("/radar"));
    expect(bar).toHaveAttribute("data-active", "true");

    navigation.pathname = "/radar";
    rerender(<NavigationProgress />);
    expect(bar).toHaveAttribute("data-active", "false");
    navigation.pathname = "/";
  });
});
