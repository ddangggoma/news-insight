"use client";

import { Maximize2, Minus, Plus } from "lucide-react";
import {
  createContext,
  type Dispatch,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
  type SetStateAction,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { DetailDialog } from "@/components/detail-dialog";
import { cn } from "@/lib/utils";

/*
 * Chart tools (2026-10-27): every chart panel can zoom (buttons, Ctrl/⌘ + wheel or pinch, drag to
 * pan), open full screen, and hide series from its legend. Zoom widens the drawing instead of
 * scaling pixels, so SVG charts stay sharp and their labels spread out.
 */

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const STEPS = [1, 1.25, 1.5, 2, 3, 4];

const clamp = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

function stepZoom(z: number, direction: 1 | -1): number {
  if (direction > 0) return STEPS.find((s) => s > z + 0.01) ?? MAX_ZOOM;
  return [...STEPS].reverse().find((s) => s < z - 0.01) ?? MIN_ZOOM;
}

// ── hidden series, shared by a panel's legends and charts ─────────────────────────────────

type Hidden = { hidden: ReadonlySet<string>; setHidden: Dispatch<SetStateAction<ReadonlySet<string>>> };
const HiddenContext = createContext<Hidden | null>(null);
const NONE: ReadonlySet<string> = new Set();

/** Series keys the panel's legend has hidden; charts drawn by a library (recharts) drop them. */
export function useHiddenSeries(): ReadonlySet<string> {
  return useContext(HiddenContext)?.hidden ?? NONE;
}

// ── zoomable viewport ─────────────────────────────────────────────────────────────────────

type Zoom = { zoom: number; setZoom: (z: number, anchorX?: number) => void };
/** Where the last zoom was aimed (null: the centre) and the zoom it started from. */
type Anchor = RefObject<{ x: number | null; from: number } | null>;

function useZoom(): Zoom & { anchor: Anchor } {
  const [zoom, set] = useState(1);
  const anchor = useRef<{ x: number | null; from: number } | null>(null);
  const setZoom = (next: number, anchorX?: number) => {
    anchor.current = { x: anchorX ?? null, from: anchor.current?.from ?? zoom };
    set(clamp(next));
  };
  return { zoom, setZoom, anchor };
}

function Viewport({
  zoom,
  setZoom,
  anchor,
  children,
  className,
}: Zoom & { anchor: Anchor; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const scope = useId();
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);
  const [panning, setPanning] = useState(false);
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const setZoomRef = useRef(setZoom);
  setZoomRef.current = setZoom;

  // Ctrl/⌘ + wheel (a trackpad pinch arrives the same way) zooms around the pointer; a plain wheel scrolls the page
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const box = node.getBoundingClientRect();
      setZoomRef.current(zoomRef.current * Math.exp(-event.deltaY * 0.01), event.clientX - box.left);
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  // keep the point under the pointer (or the centre) in place as the width changes
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const aim = anchor.current;
    anchor.current = null;
    if (!aim || aim.from === zoom) return;
    const x = aim.x ?? node.clientWidth / 2;
    node.scrollLeft = (node.scrollLeft + x) * (zoom / aim.from) - x;
  }, [zoom, anchor]);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (zoom <= 1 || event.button !== 0 || event.pointerType !== "mouse") return;
    const node = ref.current!;
    drag.current = { x: event.clientX, y: event.clientY, left: node.scrollLeft, top: node.scrollTop, moved: false };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!start.moved && Math.hypot(dx, dy) < 5) return;
    if (!start.moved) {
      start.moved = true;
      setPanning(true);
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    ref.current!.scrollLeft = start.left - dx;
    ref.current!.scrollTop = start.top - dy;
  };
  const endDrag = () => {
    setPanning(false);
    // the click that ends a drag must not follow a link under the pointer
    if (drag.current?.moved) window.setTimeout(() => (drag.current = null), 0);
    else drag.current = null;
  };
  const onClickCapture = (event: MouseEvent<HTMLDivElement>) => {
    if (drag.current?.moved) {
      event.preventDefault();
      event.stopPropagation();
      drag.current = null;
    }
  };

  return (
    <div
      ref={ref}
      data-chart-scope={scope}
      className={cn("min-w-0", zoom > 1 && "overflow-x-auto overscroll-x-contain", zoom > 1 && (panning ? "cursor-grabbing select-none" : "cursor-grab"), className)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onClickCapture={onClickCapture}
    >
      <div style={zoom > 1 ? { width: `${zoom * 100}%` } : undefined}>{children}</div>
    </div>
  );
}

function ToolButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-35"
    >
      {children}
    </button>
  );
}

function ZoomTools({ zoom, setZoom, onExpand }: Zoom & { onExpand?: () => void }) {
  return (
    <div role="toolbar" aria-label="차트 도구" className="flex items-center gap-0.5 rounded-lg border bg-background/80 p-0.5">
      <ToolButton label="축소 (−)" onClick={() => setZoom(stepZoom(zoom, -1))} disabled={zoom <= MIN_ZOOM}>
        <Minus className="size-3.5" aria-hidden />
      </ToolButton>
      <button
        type="button"
        title="원래 크기로 (0) · Ctrl/⌘ + 휠로 확대, 끌어서 이동"
        onClick={() => setZoom(1)}
        className="h-7 min-w-11 rounded-md px-1 text-xs font-semibold text-ink-2 tabular-nums transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {Math.round(zoom * 100)}%
      </button>
      <ToolButton label="확대 (+)" onClick={() => setZoom(stepZoom(zoom, 1))} disabled={zoom >= MAX_ZOOM}>
        <Plus className="size-3.5" aria-hidden />
      </ToolButton>
      {onExpand ? (
        <>
          <span aria-hidden className="mx-0.5 h-4 w-px bg-border" />
          <ToolButton label="크게 보기" onClick={onExpand}>
            <Maximize2 className="size-3.5" aria-hidden />
          </ToolButton>
        </>
      ) : null}
    </div>
  );
}

/** + / − / 0 while focus is inside the chart (not in a form field). */
function onZoomKeys(event: KeyboardEvent, { zoom, setZoom }: Zoom) {
  const target = event.target as HTMLElement;
  if (event.metaKey || event.ctrlKey || event.altKey || target.closest("input, textarea, select, [contenteditable]")) return;
  if (event.key === "+" || event.key === "=") setZoom(stepZoom(zoom, 1));
  else if (event.key === "-") setZoom(stepZoom(zoom, -1));
  else if (event.key === "0") setZoom(1);
  else return;
  event.preventDefault();
}

// ── panel ─────────────────────────────────────────────────────────────────────────────────

export function ChartPanel({
  id,
  title,
  question,
  note,
  action,
  tools = true,
  children,
  className,
}: {
  id?: string;
  title: string;
  /** The strategy question this view answers, shown under the title. */
  question?: string;
  note?: ReactNode;
  action?: ReactNode;
  /** Zoom and full-screen controls; off for panels that hold lists rather than charts. */
  tools?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const chart = useChartTools(title, question, note, children);

  return chart.provide(
    <>
      <section
        id={id}
        aria-labelledby={id ? `${id}-title` : undefined}
        className={cn("group/panel min-w-0 scroll-mt-28 rounded-2xl border bg-card p-4 shadow-xs md:p-5", className)}
        onKeyDown={tools ? chart.onKeyDown : undefined}
      >
        <header className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1">
            <h2 id={id ? `${id}-title` : undefined} className="text-[15px] font-bold tracking-tight">
              {title}
            </h2>
            {question ? <p className="mt-0.5 text-xs text-muted-foreground">{question}</p> : null}
          </div>
          {action || tools ? (
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {action}
              {tools ? chart.toolbar : null}
            </div>
          ) : null}
        </header>
        {tools ? chart.body : children}
        {note ? <p className="mt-3 border-t pt-2 text-xs leading-relaxed text-muted-foreground">{note}</p> : null}
      </section>
      {tools ? chart.dialog : null}
    </>,
  );
}

/**
 * The chart tools without the panel chrome, for charts that sit in a card of their own (the
 * AI 모델 benchmark cards): the toolbar on the right above the chart, then the chart.
 */
export function ChartFrame({ title, question, children, className }: { title: string; question?: string; children: ReactNode; className?: string }) {
  const chart = useChartTools(title, question, undefined, children);
  return chart.provide(
    <>
      <div className={cn("min-w-0", className)} onKeyDown={chart.onKeyDown}>
        <div className="mb-3 flex justify-end">{chart.toolbar}</div>
        {chart.body}
      </div>
      {chart.dialog}
    </>,
  );
}

/** State and parts shared by ChartPanel and ChartFrame: hidden series, inline and full-screen zoom. */
function useChartTools(title: string, question: string | undefined, note: ReactNode, children: ReactNode) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(NONE);
  const inline = useZoom();
  const full = useZoom();
  const [expanded, setExpanded] = useState(false);
  const [height, setHeight] = useState(0);
  const body = useRef<HTMLDivElement>(null);

  const expand = () => {
    setHeight(body.current?.offsetHeight ?? 0);
    full.setZoom(1);
    setExpanded(true);
  };

  return {
    provide: (node: ReactNode) => <HiddenContext value={{ hidden, setHidden }}>{node}</HiddenContext>,
    onKeyDown: (event: KeyboardEvent) => onZoomKeys(event, inline),
    toolbar: <ZoomTools zoom={inline.zoom} setZoom={inline.setZoom} onExpand={expand} />,
    body: (
      <div ref={body}>
        {expanded ? (
          <div style={{ height }} className="grid place-items-center rounded-xl border border-dashed text-sm text-muted-foreground">
            크게 보기 창에서 보는 중입니다
          </div>
        ) : (
          <Viewport {...inline}>{children}</Viewport>
        )}
      </div>
    ),
    dialog: (
      <DetailDialog
        open={expanded}
        onOpenChange={setExpanded}
        title={title}
        description={question}
        size="full"
        actions={<ZoomTools zoom={full.zoom} setZoom={full.setZoom} />}
      >
        <div className="space-y-4 p-5 md:p-8" onKeyDown={(event) => onZoomKeys(event, full)}>
          {question ? <p className="text-sm text-muted-foreground">{question}</p> : null}
          <Viewport {...full}>{children}</Viewport>
          {note ? <p className="max-w-[75ch] border-t pt-3 text-xs leading-relaxed text-muted-foreground">{note}</p> : null}
        </div>
      </DetailDialog>
    ),
  };
}

/**
 * Toggle helpers for a custom legend (the benchmark provider legend); null outside a chart frame.
 * Click hides a key, `solo` keeps only one of `keys` visible.
 */
export function useSeriesToggle(): {
  hidden: ReadonlySet<string>;
  toggle: (key: string) => void;
  solo: (key: string, keys: string[]) => void;
  reset: () => void;
} | null {
  const shared = useContext(HiddenContext);
  if (!shared) return null;
  const { hidden, setHidden } = shared;
  return {
    hidden,
    toggle: (key) =>
      setHidden((current) => {
        const next = new Set(current);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      }),
    solo: (key, keys) => setHidden(new Set(keys.filter((k) => k !== key))),
    reset: () => setHidden(NONE),
  };
}

// ── legend ────────────────────────────────────────────────────────────────────────────────

type LegendItem = { label: string; swatch: string; shape?: "dot" | "bar"; /** series key for library charts; defaults to the label */ key?: string };

const keyOf = (item: LegendItem) => item.key ?? item.label;

/**
 * Legend row: a swatch beside text-coloured labels. Each entry is a toggle: click hides that
 * series, double-click shows it alone. Hand-drawn SVG charts dim every mark (not text) painted in the
 * entry's swatch colour; library charts read `useHiddenSeries()`.
 */
export function Legend({ items, className }: { items: LegendItem[]; className?: string }) {
  const shared = useContext(HiddenContext);
  const [own, setOwn] = useState<ReadonlySet<string>>(NONE);
  const hidden = shared?.hidden ?? own;
  const setHidden = shared?.setHidden ?? setOwn;
  const ref = useRef<HTMLUListElement>(null);
  const fallback = useId();
  const [scope, setScope] = useState<string | null>(null);

  useEffect(() => {
    const list = ref.current;
    if (!list) return;
    const host = list.closest<HTMLElement>("[data-chart-scope]");
    if (host) return setScope(host.dataset.chartScope ?? null);
    const parent = list.parentElement;
    if (!parent) return;
    parent.dataset.chartScope = fallback;
    setScope(fallback);
  }, [fallback]);

  const toggle = (key: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const solo = (key: string) => setHidden(new Set(items.map(keyOf).filter((k) => k !== key)));

  const css = scope
    ? items
        .filter((item) => hidden.has(keyOf(item)))
        .map((item) => {
          const v = item.swatch.replace(/["\\]/g, "");
          return `[data-chart-scope="${scope}"] :is([fill="${v}"],[stroke="${v}"],[style*="${v}"]):not([data-legend-swatch],text,tspan){opacity:.07;pointer-events:none}`;
        })
        .join("")
    : "";
  const anyHidden = items.some((item) => hidden.has(keyOf(item)));

  return (
    <ul ref={ref} aria-label="범례 (눌러서 숨기기)" className={cn("flex flex-wrap items-center gap-x-1 gap-y-1 text-xs text-muted-foreground", className)}>
      {css ? <style>{css}</style> : null}
      {items.map((item) => {
        const off = hidden.has(keyOf(item));
        return (
          <li key={keyOf(item)}>
            <button
              type="button"
              aria-pressed={!off}
              title={`${item.label}: 눌러서 ${off ? "보이기" : "숨기기"}, 두 번 눌러 이것만 보기`}
              onClick={() => toggle(keyOf(item))}
              onDoubleClick={() => solo(keyOf(item))}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-1.5 py-0.5 transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                off && "text-muted-foreground line-through decoration-muted-foreground",
              )}
            >
              <span
                aria-hidden
                data-legend-swatch=""
                className={cn("inline-block transition-opacity", item.shape === "dot" ? "size-2.5 rounded-full" : "h-2.5 w-3.5 rounded-sm", off && "opacity-25")}
                style={{ background: item.swatch }}
              />
              {item.label}
            </button>
          </li>
        );
      })}
      {anyHidden ? (
        <li>
          <button
            type="button"
            onClick={() => setHidden(NONE)}
            className="rounded-md px-1.5 py-0.5 font-medium text-primary hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            모두 보기
          </button>
        </li>
      ) : null}
    </ul>
  );
}
