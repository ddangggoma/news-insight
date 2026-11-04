"use client";

import { createColumnHelper } from "@tanstack/react-table";
import { ChevronDown } from "lucide-react";
import { Popover } from "radix-ui";
import { type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { ChartFrame, useHiddenSeries } from "@/components/chart-frame";
import { DataTable } from "@/components/reader/benchmarks/data-table";
import {
  AXES,
  type Axis,
  type Plot,
  type Shade,
  bestByModel,
  buildPlot,
  defaultConfigs,
  displayName,
  effortRank,
  labelShade,
  modelShades,
} from "@/components/reader/benchmarks/deepswe-plot";
import { ChangeMark, ProviderDot, ProviderLegend, Segmented } from "@/components/reader/benchmarks/parts";
import { Button } from "@/components/ui/button";
import { formatCompact, formatUsd } from "@/lib/benchmark-types";
import type { DeepSweView, DsPoint as Point } from "@/lib/benchmark-view";
import { formatBriefingDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Effort = "best" | "all";
const TABLE_ROWS = 20;

const half = (point: Point) => (point.low !== null && point.high !== null ? (point.high - point.low) / 2 : null);

// ---- table ---------------------------------------------------------------------------

/** The table's bar scale: 0–80%, wider in steps of 20 only when a score or interval passes it. */
function barMax(points: Point[]): number {
  const top = Math.max(0, ...points.map((p) => Math.max(p.score, p.high ?? 0)));
  return Math.min(Math.max(Math.ceil(top / 20) * 20, 80), 100);
}

/** pass@1 as a bar in the maker's colour on 0–`max`, the 95% interval as a whisker over it. */
function PassBar({ point, max }: { point: Point; max: number }) {
  const at = (v: number) => `${(Math.min(Math.max(v, 0), max) / max) * 100}%`;
  const shade = labelShade(point.model);
  const ci = point.low !== null && point.high !== null ? { low: Math.max(0, point.low), high: Math.min(100, point.high) } : null;
  const label = `pass@1 ${point.score.toFixed(1)}%${ci ? `, 95% 구간 ${ci.low.toFixed(1)}–${ci.high.toFixed(1)}%` : ""}`;
  return (
    <span role="img" aria-label={label} className="relative block h-5 w-36 md:w-56" style={{ "--bar-l": shade.light, "--bar-d": shade.dark } as CSSProperties}>
      <span aria-hidden className="absolute inset-x-0 inset-y-1 bg-muted/40" />
      <span aria-hidden className="absolute inset-y-1 left-0 bg-(--bar-l) dark:bg-(--bar-d)" style={{ width: at(point.score) }} />
      {ci && (
        <>
          <span aria-hidden className="absolute top-1/2 h-px -translate-y-1/2 bg-foreground/70" style={{ left: at(ci.low), width: `calc(${at(ci.high)} - ${at(ci.low)})` }} />
          <span aria-hidden className="absolute top-[3px] bottom-[3px] w-px bg-foreground/70" style={{ left: at(ci.low) }} />
          <span aria-hidden className="absolute top-[3px] bottom-[3px] w-px bg-foreground/70" style={{ left: at(ci.high) }} />
        </>
      )}
    </span>
  );
}

const col = createColumnHelper<Point>();

function buildColumns(max: number) {
  return [
    col.accessor("model", {
      header: "모델",
      meta: { label: "모델" },
      enableHiding: false,
      cell: ({ row: { original: p } }) => (
        <span className="flex items-center gap-1.5">
          <ProviderDot provider={p.provider} />
          <span className="font-medium">{displayName(p.model)}</span>
          {p.effort && <span className="rounded border px-1 text-[10px] text-muted-foreground">{p.effort}</span>}
          <ChangeMark change={p.change} by={p.changeBy} />
        </span>
      ),
    }),
    col.display({
      id: "bar",
      header: () => (
        <span className="flex w-36 justify-between font-normal tabular-nums md:w-56" aria-label={`0–${max}% 눈금`}>
          <span>0%</span>
          <span>{`${max}%`}</span>
        </span>
      ),
      meta: { label: "막대" },
      enableSorting: false,
      cell: ({ row: { original: p } }) => <PassBar point={p} max={max} />,
    }),
    col.accessor("score", {
      header: "pass@1",
      meta: { label: "pass@1", numeric: true },
      cell: ({ row: { original: p } }) => (
        <span className="inline-flex items-baseline gap-1">
          <span className="font-semibold">{p.score.toFixed(1)}</span>
          {half(p) !== null && <span className="text-[11px] text-muted-foreground">{`±${half(p)!.toFixed(1)}`}</span>}
        </span>
      ),
    }),
    col.accessor((p) => p.cost ?? undefined, { id: "cost", header: "평균 비용", meta: { label: "평균 비용", numeric: true }, cell: ({ row }) => formatUsd(row.original.cost) }),
    col.accessor((p) => p.tokens ?? undefined, { id: "tokens", header: "출력 토큰", meta: { label: "출력 토큰", numeric: true }, cell: ({ row }) => formatCompact(row.original.tokens) }),
    col.accessor((p) => p.steps ?? undefined, {
      id: "steps",
      header: "단계",
      meta: { label: "단계", numeric: true },
      cell: ({ row }) => (row.original.steps === null ? "—" : row.original.steps.toFixed(0)),
    }),
  ];
}

// ---- configs picker ------------------------------------------------------------------

function Indeterminate({ checked, mixed, ...props }: { checked: boolean; mixed: boolean; id: string; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = mixed;
  }, [mixed]);
  return <input ref={ref} type="checkbox" checked={checked} className="size-3.5 accent-primary" {...props} />;
}

/** The site's "Configs (shown/total)": a model's box toggles all its effort levels, a chip one. */
function ConfigPicker({ points, selected, onChange }: { points: Point[]; selected: Set<string>; onChange: (next: Set<string>) => void }) {
  const models = useMemo(
    () =>
      bestByModel(points).map(({ model }) => ({
        model,
        configs: points.filter((p) => p.model === model).sort((a, b) => effortRank(a.effort) - effortRank(b.effort)),
      })),
    [points],
  );
  const toggle = (ids: string[]) => {
    const next = new Set(selected);
    const all = ids.every((id) => next.has(id));
    for (const id of ids) (all ? next.delete(id) : next.add(id));
    onChange(next);
  };
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button type="button" variant="outline" size="xs" aria-label="구성 고르기" className="group">
          <span>구성</span>
          <span className="text-muted-foreground tabular-nums">{`(${selected.size}/${points.length})`}</span>
          <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={4}
          className="z-50 flex max-h-[420px] w-[300px] flex-col rounded-lg bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10"
        >
          <ul aria-label="모델별 구성" className="flex-1 overflow-auto py-1">
            {models.map(({ model, configs }) => {
              const on = configs.filter((p) => selected.has(p.id)).length;
              const id = `dsw-cfg-${model}`;
              return (
                <li key={model} className="px-3 py-1.5 hover:bg-accent">
                  <label htmlFor={id} className="flex cursor-pointer items-center gap-2 text-xs">
                    <Indeterminate id={id} checked={on === configs.length} mixed={on > 0 && on < configs.length} onChange={() => toggle(configs.map((p) => p.id))} />
                    <span className="flex-1 font-medium">{displayName(model)}</span>
                    <span className="text-[11px] text-muted-foreground tabular-nums">{`${on}/${configs.length}`}</span>
                  </label>
                  {configs.length > 1 && (
                    <div className="mt-1 ml-6 flex flex-wrap gap-1">
                      {configs.map((p) => {
                        const pressed = selected.has(p.id);
                        return (
                          <button
                            key={p.id}
                            type="button"
                            aria-pressed={pressed}
                            onClick={() => toggle([p.id])}
                            title={`${p.effort ?? "기본"} · ${formatUsd(p.cost)} · ${p.score.toFixed(0)}%`}
                            className={cn(
                              "rounded-sm border px-1.5 py-px font-mono text-[10px] tracking-[0.08em] uppercase transition-colors",
                              pressed ? "border-foreground/70 bg-foreground/5 text-foreground" : "text-muted-foreground/70 line-through hover:text-foreground",
                            )}
                          >
                            {p.effort ?? "기본"}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          <div className="flex items-center gap-2 border-t px-3 py-2">
            <button type="button" onClick={() => onChange(new Set(points.map((p) => p.id)))} className="rounded-sm border px-2 py-1 text-[11px] font-medium hover:bg-accent">
              전체 선택
            </button>
            <button type="button" onClick={() => onChange(new Set())} className="rounded-sm border px-2 py-1 text-[11px] font-medium hover:bg-accent">
              모두 해제
            </button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

// ---- chart ---------------------------------------------------------------------------

/** The container's width once mounted (null when it measures 0); undefined until then. */
function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | null | undefined>(undefined);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth || null);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/**
 * One class per model carrying its colours: `--c` the mark, `--c2` the softer line and
 * unlabelled-dot tint, `--lc` the label (the maker's own colour); dark theme values beside.
 */
function colourCss(order: string[], shades: Map<string, Shade>): string {
  return order
    .map((model, i) => {
      const mark = shades.get(model) ?? labelShade(model);
      const text = labelShade(model);
      return `.dsw-m${i}{--c:${mark.light};--lc:${text.light};--c2:color-mix(in oklab,var(--c) 84%,var(--card))}.dark .dsw-m${i}{--c:${mark.dark};--lc:${text.dark}}`;
    })
    .join("");
}

const HALO = { paintOrder: "stroke", stroke: "var(--card)", strokeLinejoin: "round" } as const;

/**
 * DeepSWE's chart: pass rate against cost, output tokens or agent steps per task, the x axis
 * running from dear on the left to cheap on the right so the efficient corner is top right.
 * A model's effort levels are joined in effort order; one point per model is labelled.
 * Hover (or click to pin) picks a model out and reads its exact values off both axes.
 */
function ScorePlot({ rows, axis, shades }: { rows: Point[]; axis: Axis; shades: Map<string, Shade> }) {
  const [ref, width] = useWidth();
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<{ id: string; model: string } | null>(null);
  const titleId = useId();
  const descId = useId();
  const plot: Plot | null = useMemo(() => (width === undefined ? null : buildPlot(rows, axis, width)), [rows, axis, width]);
  const order = useMemo(() => [...shades.keys()], [shades]);
  const css = useMemo(() => colourCss(order, shades), [order, shades]);
  const cls = (model: string) => `dsw-m${order.indexOf(model)}`;

  useEffect(() => {
    if (pinned && plot && !plot.points.some((p) => p.model === pinned.model)) setPinned(null);
  }, [pinned, plot]);
  useEffect(() => {
    if (!pinned) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPinned(null);
    const onClick = (e: MouseEvent) => {
      const target = e.target instanceof Element ? e.target : null;
      if (ref.current?.contains(target) || target?.closest("[data-chart-pin-source]")) return;
      setPinned(null);
      setHovered(null);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick);
    };
  }, [pinned, ref]);

  if (width === undefined) return <div ref={ref} className="aspect-[1.6] w-full" />;
  if (!plot)
    return (
      <div ref={ref} className="flex h-72 items-center justify-center text-sm text-muted-foreground">
        이 지표의 자료가 없습니다.
      </div>
    );

  const { dims: d, points, lines, labels, xTicks, yTicks, X, Y } = plot;
  const { M, font } = d;
  const metric = AXES[axis];
  const pin = (id: string) => {
    if (pinned?.id === id) {
      setHovered(null);
      setPinned(null);
      return;
    }
    const model = points.find((p) => p.id === id)?.model;
    if (model) setPinned({ id, model });
  };
  const pinnedPoint = pinned
    ? (points.find((p) => p.id === pinned.id) ?? points.find((p) => p.model === pinned.model && p.labeled) ?? points.find((p) => p.model === pinned.model) ?? null)
    : null;
  const hoverPoint = hovered ? (points.find((p) => p.id === hovered) ?? null) : null;
  const active = pinnedPoint ? (hoverPoint && hoverPoint.model === pinnedPoint.model ? hoverPoint : pinnedPoint) : hoverPoint;
  const focus = active?.model ?? null;
  const dim = (model: string): CSSProperties | undefined => (focus !== null && model !== focus ? { opacity: 0.55, filter: "grayscale(1)" } : undefined);
  const last = <T extends { model: string }>(items: T[]) => (focus === null ? items : [...items].sort((a, b) => (a.model === focus ? 1 : 0) - (b.model === focus ? 1 : 0)));
  // hide the regular tick labels the exact values would sit on
  const valueHalf = active ? (metric.format(active.x).length * font.hover * 0.62) / 2 : 0;
  const xClash = (v: number) => active !== null && Math.abs(X(v) - active.px) < valueHalf + (metric.format(v).length * font.tick * 0.62) / 2 + 6;
  const yClash = (v: number) => active !== null && Math.abs(Y(v) - active.py) < (font.tick + font.hover) / 2 + 4;
  const bottom = M.top + d.plotH;
  const handlers = (id: string) => ({
    onMouseEnter: () => setHovered(id),
    onMouseLeave: () => setHovered(null),
    onClick: (e: ReactMouseEvent) => {
      e.stopPropagation();
      pin(id);
    },
  });
  const fade = "transition-[opacity,filter] duration-150";
  // the labelled point of each model takes focus: focus reads like hover, Enter/Space pins
  const keys = (p: (typeof points)[number]) => ({
    tabIndex: 0,
    role: "button",
    "aria-pressed": pinned?.id === p.id,
    "aria-label": `${displayName(p.model)}${p.effort ? ` ${p.effort}` : ""}: pass@1 ${(p.y * 100).toFixed(1)}%, ${metric.title} ${metric.format(p.x)}`,
    onFocus: () => setHovered(p.id),
    onBlur: () => setHovered(null),
    onKeyDown: (e: ReactKeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pin(p.id);
      } else if (e.key === "Escape") {
        setPinned(null);
        setHovered(null);
      }
    },
  });

  return (
    <div ref={ref} className="w-full">
      <svg
        viewBox={`0 0 ${d.W} ${d.H}`}
        width="100%"
        role="group"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="block"
        onMouseLeave={() => setHovered(null)}
        onClick={() => {
          setPinned(null);
          setHovered(null);
        }}
      >
        <title id={titleId}>{`DeepSWE 점수와 ${metric.title}`}</title>
        <desc id={descId}>
          {`모델 구성마다 pass@1(세로축)과 ${metric.title}(가로축, 오른쪽일수록 적음)을 점으로 찍고, 한 모델의 추론 강도들을 선으로 이었습니다. 같은 자료가 아래 DeepSWE 순위표에 있습니다.`}
        </desc>
        <style>{css}</style>
        <text x={M.left} y={M.top - 16} fontSize={font.title} fontWeight={600} className="fill-foreground">
          DeepSWE 점수
        </text>
        {xTicks.map((v) => (
          <g key={`x${v}`}>
            <line x1={X(v)} x2={X(v)} y1={M.top} y2={bottom} stroke="var(--muted-foreground)" opacity={0.25} />
            {!xClash(v) && (
              <text x={X(v)} y={bottom + 18} textAnchor="middle" fontSize={font.tick} className="fill-muted-foreground">
                {metric.format(v)}
              </text>
            )}
          </g>
        ))}
        {yTicks.map((v) => (
          <g key={`y${v}`}>
            <line x1={M.left} x2={M.left + d.plotW} y1={Y(v)} y2={Y(v)} stroke="var(--muted-foreground)" opacity={0.25} />
            {!yClash(v) && (
              <text x={M.left - 10} y={Y(v) + 4} textAnchor="end" fontSize={font.tick} className="fill-muted-foreground">
                {`${Math.round(v * 100)}%`}
              </text>
            )}
          </g>
        ))}
        <text x={M.left + d.plotW / 2} y={d.H - 14} textAnchor="middle" fontSize={font.axis} className="fill-foreground">
          {metric.title}
        </text>
        <text x={M.left + d.plotW - 6} y={M.top + 15} textAnchor="end" fontSize={font.eff} fontStyle="italic" className="fill-muted-foreground">
          효율 높음 ↗
        </text>

        {last(lines).map((line) => (
          <g key={`l${line.key}`} className={cls(line.model)} data-line={line.model}>
            <path
              d={line.d}
              fill="none"
              stroke="transparent"
              strokeWidth={12}
              strokeLinecap="round"
              strokeLinejoin="round"
              pointerEvents="stroke"
              className="cursor-pointer"
              {...handlers(line.hoverId)}
            />
            <path d={line.d} fill="none" stroke="var(--c2)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" pointerEvents="none" className={fade} style={dim(line.model)} />
          </g>
        ))}

        {active && (
          <g pointerEvents="none" className={cls(active.model)}>
            <line x1={active.px} y1={active.py} x2={active.px} y2={bottom} stroke="var(--c)" strokeWidth={1} strokeDasharray="4 4" />
            <line x1={M.left} y1={active.py} x2={active.px} y2={active.py} stroke="var(--c)" strokeWidth={1} strokeDasharray="4 4" />
            <text x={active.px} y={bottom + 18} textAnchor="middle" fontSize={font.hover} fontWeight={600} fill="var(--c)" style={{ ...HALO, strokeWidth: 4 }}>
              {metric.format(active.x)}
            </text>
            <text x={M.left - 10} y={active.py + 4} textAnchor="end" fontSize={font.hover} fontWeight={600} fill="var(--c)" style={{ ...HALO, strokeWidth: 4 }}>
              {`${(active.y * 100).toFixed(0)}%`}
            </text>
          </g>
        )}

        {/* points keep their order (a moved node would lose keyboard focus); the picked model's dots are redrawn on top */}
        {points.map((p) => (
          <g
            key={p.id}
            data-point={p.model}
            className={cn(cls(p.model), fade, "cursor-pointer focus:outline-none focus-visible:[&>circle:last-child]:stroke-foreground focus-visible:[&>circle:last-child]:stroke-2")}
            style={dim(p.model)}
            {...handlers(p.id)}
            {...(p.labeled ? keys(p) : {})}
          >
            <circle cx={p.px} cy={p.py} r={14} fill="transparent" />
            <circle cx={p.px} cy={p.py} r={active?.id === p.id ? 6 : 4} fill={p.labeled ? "var(--c)" : "var(--c2)"} />
          </g>
        ))}
        {focus !== null && (
          <g aria-hidden pointerEvents="none" className={cls(focus)}>
            {points
              .filter((p) => p.model === focus)
              .map((p) => (
                <circle key={p.id} cx={p.px} cy={p.py} r={active?.id === p.id ? 6 : 4} fill={p.labeled ? "var(--c)" : "var(--c2)"} />
              ))}
          </g>
        )}

        {active && !active.labeled && active.effort && (
          <text
            x={active.px + 11}
            y={active.py + 4}
            fontSize={font.eff * 0.82}
            fill="var(--c)"
            pointerEvents="none"
            className={cn(cls(active.model), "font-mono tracking-[0.08em]")}
            style={{ ...HALO, strokeWidth: 3 }}
          >
            {active.effort.toUpperCase()}
          </text>
        )}

        {last([...labels].reverse()).map((label) => (
          <g key={`t${label.id}`} data-label={label.model} className={cn(cls(label.model), fade, "cursor-pointer")} style={dim(label.model)} {...handlers(label.id)}>
            {label.leader && (
              <line
                x1={label.px}
                y1={label.py}
                x2={label.anchor === "middle" ? label.x : label.anchor === "start" ? label.x - 1 : label.x + 1}
                y2={label.y - 2}
                stroke="var(--lc)"
                strokeWidth={1}
                opacity={0.35}
              />
            )}
            <text x={label.x} y={label.y} textAnchor={label.anchor} fontSize={font.label} fontWeight={600} fill="var(--lc)" style={{ ...HALO, strokeWidth: 3.5 }}>
              {label.line1}
            </text>
            {label.line2 && (
              <text
                x={label.x}
                y={label.y + 10}
                textAnchor={label.anchor}
                fontSize={font.eff * 0.82}
                fill="var(--lc)"
                opacity={0.6}
                className="font-mono tracking-[0.08em]"
                style={{ ...HALO, strokeWidth: 3 }}
              >
                {label.line2.toUpperCase()}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

/**
 * The plot and its provider legend, inside the chart frame: a provider switched off in the
 * legend leaves the plot (its dots, lines and labels) but stays in the legend.
 */
function ScoreChart({ rows, axis, shades }: { rows: Point[]; axis: Axis; shades: Map<string, Shade> }) {
  const hidden = useHiddenSeries();
  const plotted = useMemo(() => rows.filter((p) => !hidden.has(p.provider)), [rows, hidden]);
  return (
    <div className="space-y-2">
      <div className="rounded-lg border bg-card p-2 sm:p-3">
        <ScorePlot rows={plotted} axis={axis} shades={shades} />
      </div>
      <ProviderLegend providers={rows.map((p) => p.provider)} />
    </div>
  );
}

/**
 * DeepSWE's own page: the version and x-metric toggles over its score chart (configurations
 * picked in "구성"), then its table with a pass@1 bar per row.
 */
export function DeepSweChart({ view }: { view: DeepSweView }) {
  // the newest version first, as the site opens on it
  const [board, setBoard] = useState(view.boards[0] ?? "");
  const [axis, setAxis] = useState<Axis>("cost");
  const [effort, setEffort] = useState<Effort>("best");
  const [picked, setPicked] = useState<Record<string, string[]>>({});

  const onBoard = useMemo(() => view.points.filter((p) => p.board === board), [view.points, board]);
  const defaults = useMemo(() => defaultConfigs(onBoard), [onBoard]);
  const selected = useMemo(() => (picked[board] ? new Set(picked[board]) : defaults), [picked, board, defaults]);
  const shown = useMemo(() => onBoard.filter((p) => selected.has(p.id)), [onBoard, selected]);
  const shades = useMemo(() => modelShades(onBoard), [onBoard]);
  const tableRows = useMemo(() => onBoard.filter((p) => effort === "all" || p.best), [onBoard, effort]);
  const columns = useMemo(() => buildColumns(barMax(tableRows)), [tableRows]);
  const info = view.info[board];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex flex-wrap items-center gap-2">
          {view.boards.length > 1 && <Segmented label="버전" options={view.boards.map((b) => ({ key: b, label: b }))} value={board} onChange={setBoard} />}
          <Segmented label="가로축" options={(Object.keys(AXES) as Axis[]).map((key) => ({ key, label: AXES[key].label }))} value={axis} onChange={setAxis} />
        </div>
        <div className="ml-auto flex items-center gap-3">
          {(info?.tasks || info?.updated) && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {info.tasks ? <span className="text-foreground">{`과제 ${info.tasks}개`}</span> : null}
              {info.updated ? (
                <>
                  {info.tasks ? " · " : ""}
                  {"갱신 "}
                  <span className="text-foreground">{formatBriefingDate(info.updated)}</span>
                </>
              ) : null}
            </span>
          )}
          <ConfigPicker points={onBoard} selected={selected} onChange={(next) => setPicked((prev) => ({ ...prev, [board]: [...next] }))} />
        </div>
      </div>

      <ChartFrame title="DeepSWE 점수">
        <ScoreChart key={board} rows={shown} axis={axis} shades={shades} />
      </ChartFrame>

      <DataTable
        label="DeepSWE 순위표"
        columns={columns}
        data={tableRows}
        getRowId={(p) => p.id}
        initialSorting={[{ id: "score", desc: true }]}
        initialLimit={TABLE_ROWS}
        toolbar={
          <Segmented
            label="추론 강도"
            options={[
              { key: "best", label: "최고값만" },
              { key: "all", label: "모든 추론 강도" },
            ]}
            value={effort}
            onChange={setEffort}
          />
        }
      />
    </div>
  );
}
